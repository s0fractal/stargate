//! Bounded traces through an unchanged production Outbox and real Unix sockets.
#[path = "delivery.rs"]
mod delivery;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixListener;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use std::time::Duration;

const SUBJECT: &str = "SIGNAL#trace-1:test|203.0.113.1|-|trace";

fn main() {
    let cases: &[(&str, &[(&str, &[u8])])] = &[
        (
            "unknown_duplicate",
            &[
                ("unknown", b"OK unexpected\n"),
                ("duplicate", b"OK duplicate\n"),
            ],
        ),
        (
            "partial_applied",
            &[("partial", b"OK applied"), ("applied", b"OK applied\n")],
        ),
        (
            "eof_recorded",
            &[("eof", b""), ("recorded", b"OK recorded\n")],
        ),
        (
            "two_failures_duplicate",
            &[
                ("unknown", b"OK unexpected\n"),
                ("eof", b""),
                ("duplicate", b"OK duplicate\n"),
            ],
        ),
        ("applied_empty", &[("applied", b"OK applied\n")]),
    ];
    let dir = std::env::temp_dir().join(format!("sg-traces-{}", std::process::id()));
    std::fs::create_dir(&dir).unwrap();
    for &(name, responses) in cases {
        let path = dir.join(name);
        let listener = UnixListener::bind(&path).unwrap();
        listener.set_nonblocking(true).unwrap();
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let node = std::thread::spawn(move || {
            let mut index = 0;
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
                    assert_eq!(line.trim(), SUBJECT);
                    // Extra sends remain observable under a retain-after-ACK mutant.
                    let reply = responses
                        .get(index)
                        .map(|(_, reply)| *reply)
                        .unwrap_or(b"OK duplicate\n");
                    index += 1;
                    stream.write_all(reply).unwrap();
                    if !reply.ends_with(b"\n") || reply == b"OK unexpected\n" {
                        break;
                    }
                }
            }
        });
        let mut out = delivery::Outbox::new(&path, 2);
        out.push(SUBJECT);
        let mut total = 0;
        let mut identity = true;
        for (step, &(event, _)) in responses.iter().enumerate() {
            if step > 0 {
                // Production backoff is 500ms, then 1000ms; no test-only source rewrite.
                std::thread::sleep(Duration::from_millis(550 * (1 << (step - 1))));
            }
            let (done, error) = out.flush(1);
            total += done.len();
            identity &= done.iter().all(|(line, _)| line == SUBJECT);
            println!(
                "{name}\t{step}\t{event}\t{}\t{total}\t{}\t{}\t{identity}",
                out.pending(),
                out.lost,
                error.is_some()
            );
        }
        let (done, error) = out.flush(1);
        total += done.len();
        identity &= done.iter().all(|(line, _)| line == SUBJECT);
        println!(
            "{name}\t{}\tempty\t{}\t{total}\t{}\t{}\t{identity}",
            responses.len(),
            out.pending(),
            out.lost,
            error.is_some()
        );
        drop(out);
        stop.store(true, Ordering::SeqCst);
        node.join().unwrap();
    }
    std::fs::remove_dir_all(dir).unwrap();
}
