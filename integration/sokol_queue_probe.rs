//! Capacity-two observations of the unchanged production Outbox.
#[path = "delivery.rs"]
mod delivery;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixListener;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::time::Duration;

fn main() {
    let cases: &[(&str, &[&str])] = &[
        (
            "fifo_limit",
            &[
                "push:A1", "push:B1", "flush:0", "flush:1", "push:A2", "flush:8", "flush:8",
            ],
        ),
        (
            "partial_retry",
            &[
                "push:A1", "push:B1", "flush:2", "push:A2", "retry:2", "flush:8",
            ],
        ),
        (
            "overflow",
            &["push:A1", "push:B1", "push:A2", "flush:8", "flush:8"],
        ),
        (
            "repeated_overflow",
            &[
                "push:A1", "push:B1", "push:A2", "push:B2", "flush:1", "flush:8",
            ],
        ),
    ];
    let dir = std::env::temp_dir().join(format!("sg-queue-{}", std::process::id()));
    std::fs::create_dir(&dir).unwrap();
    for &(name, ops) in cases {
        let path = dir.join(name);
        let listener = UnixListener::bind(&path).unwrap();
        listener.set_nonblocking(true).unwrap();
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let requests = Arc::new(Mutex::new(Vec::<String>::new()));
        let wire = requests.clone();
        let node = std::thread::spawn(move || {
            let mut failed_b = false;
            while !stopping.load(Ordering::SeqCst) {
                let (mut stream, _) = match listener.accept() {
                    Ok(pair) => pair,
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(Duration::from_millis(2));
                        continue;
                    }
                    Err(e) => panic!("accept: {e}"),
                };
                stream
                    .set_read_timeout(Some(Duration::from_millis(100)))
                    .unwrap();
                let mut reader = BufReader::new(stream.try_clone().unwrap());
                while !stopping.load(Ordering::SeqCst) {
                    let mut line = String::new();
                    match reader.read_line(&mut line) {
                        Ok(0) => break,
                        Ok(_) => {}
                        Err(e)
                            if matches!(
                                e.kind(),
                                std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                            ) =>
                        {
                            continue
                        }
                        Err(e) => panic!("read: {e}"),
                    }
                    if line.trim() == "ACK" {
                        stream.write_all(b"OK ack\n").unwrap();
                        continue;
                    }
                    let id = subject(line.trim());
                    wire.lock().unwrap().push(id.to_owned());
                    if name == "partial_retry" && id == "B1" && !failed_b {
                        failed_b = true;
                        stream.write_all(b"OK unknown\n").unwrap();
                        break;
                    }
                    let reply: &[u8] = if failed_b && id == "B1" {
                        b"OK duplicate\n"
                    } else {
                        b"OK applied\n"
                    };
                    stream.write_all(reply).unwrap();
                }
            }
        });
        let mut out = delivery::Outbox::new(&path, 2);
        for (step, &op) in ops.iter().enumerate() {
            let (kind, value) = op.split_once(':').unwrap();
            let (done, error) = if kind == "push" {
                out.push(&format!("SIGNAL#{value}:test|203.0.113.1|-|queue"));
                (Vec::new(), None)
            } else {
                if kind == "retry" {
                    std::thread::sleep(Duration::from_millis(550));
                }
                out.flush(value.parse().unwrap())
            };
            let done = done
                .iter()
                .map(|(line, _)| subject(line).to_owned())
                .collect::<Vec<_>>()
                .join(",");
            let wire = requests.lock().unwrap().join(",");
            println!(
                "{name}\t{step}\t{op}\t{}\t{}\t{done}\t{wire}\t{}",
                out.pending(),
                out.lost,
                error.is_some()
            );
        }
        drop(out);
        stop.store(true, Ordering::SeqCst);
        node.join().unwrap();
    }
    std::fs::remove_dir_all(dir).unwrap();
}

fn subject(line: &str) -> &str {
    line.strip_prefix("SIGNAL#")
        .unwrap()
        .split_once(':')
        .unwrap()
        .0
}
