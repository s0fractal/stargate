# Stargate: переносний світ, відкритий до змін

> Генерація — вільна. Допуск — за явними правилами. Продовження світу не потребує дозволу його автора.

Це напрям розвитку, не специфікація вже реалізованих можливостей.
Чинну поведінку визначає [SPEC.md](SPEC.md), структуру коду —
[ARCHITECTURE.md](ARCHITECTURE.md). Stargate лишається чернеткою 32K;
цей документ нічого не заморожує.

## Світ, який можна передати в чат

Бажаний досвід: людина передає пакет у звичайний вебчат. Модель отримує
достатньо контексту, щоб зрозуміти мову світу, його поточний стан,
зобов'язання та приклади. Вона може запропонувати новий терм, контрприклад,
гіпотезу інваріанта або зміну реалізації — просто відповіддю в чаті.
Для створення пропозиції не потрібні плагін, обліковий запис у нашому сервісі,
ключ засновника чи доступ на запис у репозиторій.

Пакет має містити дві узгоджені поверхні:

- Читабельний вступ: що це за світ, його словник, приклади та спосіб відповісти.
- Точний матеріал: граматику, стан і батьківські ідентифікатори, область
  тверджень, зобов'язання, правила перевірки та потрібні для неї байти.

Проза допомагає запропонувати кандидата; точний контракт визначає його допуск.
Пакет не може гарантувати, що будь-яка модель усе зрозуміє, але не повинен
потребувати прихованої історії розмов або доступу до автора для тлумачення правил.
Інструкції всередині пакета описують участь у світі, а не надають повноважень
над середовищем отримувача.

Мінімальний транспорт — текстова відповідь, яку можна скопіювати й передати
іншому учаснику. Автоматичні канали можна додати пізніше; адреса сервера
засновника не повинна бути умовою валідності. Якщо чат не вміє виконувати код,
модель повертає **неперевірену пропозицію**. Вона копіює надані ідентифікатори,
а не вигадує обчислені хеші, результати запусків чи докази. Запуск виконує
учасник із потрібним середовищем; отримати пакет не означає виконати його код.

Для першого експерименту пропозиція має лише скопійований `parent` та
текст `candidate`. Ідентифікатор батька зв'язує її з контрактом світу.
Полів для заявлених хешів кандидата, ATP, вердикту чи доказу немає:
перевіряч обчислює ці значення сам. Цю форму реалізовано в лабораторії build 15.

## Що саме засновник не може заборонити

Ціль — відсутність персонального вето в контракті допуску. За тих самих
зафіксованих правил, стану й доказів результат не залежить від автора кандидата
або згоди власника репозиторію. Підпис може засвідчувати походження; для цього
класу пропозицій він не є перепусткою від засновника.

Сьогодні `verify_record` вимагає довіреного ключа, який обирає отримувач,
а не засновник. Окремий `lab-check` уже перевіряє скінченне відтворюване
твердження без довірених підписантів. Необов'язковий підпис засвідчує
авторство байтів, а не правильність твердження. Це не послаблює чинні
вимоги довіри до підписаних суджень чи допуску зовнішніх артефактів.

Якщо кандидат задовольняє контракт світу, будь-який учасник має змогу
самостійно перевірити його та побудувати наступника. Засновник може не
розмістити цю гілку на своєму сервері або не запустити її на своїй машині.
Але така відмова не робить кандидата невалідним і не позбавляє інших
можливості продовжити світ із наявної копії.

Це потребує переносних байтів, дозволу на їх поширення й незалежного
перевіряча. Хеш сам по собі не забезпечує доступності: втрачені або
заблоковані всі копії неможливо відновити з адреси. Платформа чату також
може обмежувати відповіді; протокол не скасовує її контроль над власним сервісом.

Кілька несумісних наступників можуть одночасно бути валідними. Спільний
предок зберігається, гілки називаються явно. Єдина глобальна «головна гілка»
не є передумовою розвитку. Якщо правила змінено, це інший контракт;
ним не можна заднім числом оголосити неправильним результат за старими правилами.

## Мутагенність із перевірними наслідками

Генератори можуть бути довільними: модель, людина, перебір, мутація AST,
пошук контрприкладів. Їхня переконливість не дає їм повноважень.

Цикл розвитку має бути таким:

1. Зафіксувати батьківський стан, контракт, перевіряча й область пошуку.
2. Запропонувати кандидата або нову гіпотезу.
3. Перевірити заявлені зобов'язання незалежно від генератора.
4. Зберегти підтвердження, конкретний контрприклад або незавершений результат.
5. Побудувати допустимого наступника, зберігши предка та матеріал перевірки.

Знайдений контрприклад уточнює знання про стару заяву. Сам по собі він ще
не доводить правильності запропонованого ремонту. Згенерований інваріант
спочатку є гіпотезою; він не стає обов'язковим правилом лише тому,
що наявні приклади йому не суперечать.

Пам'ять такого середовища — переносні випадки: що стверджували, на яких
байтах перевіряли, що спростувало твердження, який ремонт витримав контроль.
Повторний учасник може перевірити випадок без довіри до переказу попереднього.
Досвід допомагає пошуку, але не стає прихованим джерелом нових законів.

## У якому сенсі гейт — математика

Бажаний гейт — машинно перевірне зобов'язання з явною областю застосування,
а не голосування рев'юверів. Люди обирають питання й область; перевіряється
точне твердження всередині них. Доказ еквівалентності програм не доводить,
що їхня спільна поведінка корисна або що вхідні твердження про світ правдиві.

Для скінченного домену можна перевірити кожен вхід. Для ширшого твердження
потрібні визначена система доведення й перевіряний доказ. Відсутність
контрприкладу за бюджет пошуку означає лише відсутність знайденого
контрприкладу. Зелені регресійні тести не означають збереження всіх теорем.

Перевіряч і його семантика входять до основи довіри. Кандидат не може
підмінити їх власною версією, а потім сам себе допустити. Зміна перевіряча
потребує окремого обґрунтування переходу; незавершена перевірка лишається
незавершеною. Поки це не реалізовано, незалежне рев'ю потрібне, щоб ловити
розбіжності між заявленим предикатом та його кодом.

ATP обмежує семантичну роботу, але сам по собі не доводить межі часу CPU
чи пам'яті. `atp_exhausted` може бути очікуваним результатом окремого чека;
це не доказ завершення обчислення чи еквівалентності. Для допуску, який
вимагає завершення, вичерпаний бюджет не можна зарахувати як успіх.

## Перший повний експеримент

Реалізований у build 15 перший крок — вузький світ булевих програм із не більш
ніж вісьмома входами. Пакет містить батьківську програму, мову кандидатів,
точну семантику й умову допуску. Генератор пропонує іншу програму;
перевіряч порівнює їх на всіх призначеннях входів — не більш ніж 256.

Програма в цьому експерименті — WPL-текст із явно заданими іменами входів.
Парсер і lowering закріплені за хешами та входять до основи довіри.
Нинішній компілятор підставляє факти, тому кожне призначення дає окремий
замкнений терм. Єдиного параметризованого SKI-терма тут не заявляємо.

Семантична перевірка має три результати:

- `equivalent`: усі призначення перевірено, обидві програми завершилися
  булевими результатами, і результати збігаються на кожному вході.
- `counterexample`: є конкретний вхід із двома завершеними різними результатами.
- `incomplete`: контрприкладу не отримано, але повної перевірки немає,
  зокрема через вичерпання ATP чи локальних ресурсів.

Некоректна форма пропозиції відхиляється до цієї семантичної класифікації.
Розбіжність реалізацій перевіряча теж зупиняє допуск; її не приписують
кандидатові як контрприклад. Незавершене обчислення не зараховується як збіг.
Окремий контроль навмисно зменшує бюджет для коректної програми й вимагає
`incomplete`. Реалізація має розрізняти невалідне правило та вичерпання
бюджету: build 15 розрізняє `PolicyError` та його окремий підклас
`CompileIncomplete`; загального перехоплення `PolicyError` недостатньо.

Якщо мета — оптимізація, контракт
заздалегідь задає метрику, наприклад строго менший максимальний ATP на
цьому ж домені. Сам збіг відповідей ще не означає поліпшення.

Критерій успіху експерименту: інший учасник отримав пакет без історії чату,
запропонував кандидата, відтворив перевірку й побудував наступника без
ключа або сервера засновника. Окремий контроль має показати, що хибний
кандидат відхиляється з відтворюваним контрприкладом.

Незалежність від ключа й сервера засновника перевіряється окремо від
незалежності реалізації. Критерій успіху також вимагає другого булевого
обчислювача з незалежним розбором WPL, без використання парсера,
lowering чи інтерпретатора першого. На всіх входах звіряються результати
обох програм. Контроль незалежного обчислювача навмисно псує спільний
парсер першого — наприклад, читає `||` як `&&`. На `a || b` із різними
значеннями входів внутрішні інтерпретатор і lowering першого мають
погодитися між собою, але порівняння з другим обчислювачем має виявити
різні відповіді. Контроль повинен досягнути саме цього порівняння;
рання відмова першого перевіряча не зараховується як його успіх.

Окремий контроль псує lowering `&&` на `||` і на `a && b` із різними
значеннями входів очікує `CompilerBug` від внутрішньої звірки першого
перевіряча. Він перевіряє цей запобіжник, а не незалежність другого.
Згода двох реалізацій посилює перевірку, але не усуває
довіру до визначення мови та правильності самих перевірячів.
Цей скінченний цикл і контролі реалізовано в build 15. Незалежне джерело
runtime digest і довіра до Python лишаються явними передумовами офлайн-перевірки.
Пакет не може засвідчити правильність власного перевіряча сам собою.

## На що спираємося сьогодні

Stargate вже має редукцію й квитанції, явне середовище обчислення,
підписані записи, прив'язку правила та фактів, переносні bundles,
допуск артефактів і пакети контрприкладів. Пакет контрприкладу сьогодні
можна перевірити на цілісність і розпакувати; це не автоматичне підтвердження
його тверджень, не пісочниця й не виконаний цикл еволюції.

Скінченна лабораторія вже має контракт, пропозицію та перевірний перехід.
Наступний шар — пошук кандидатів із пам'яттю контрприкладів. Build 16 пропонує
обмежений пошук локальних змін WPL: попередні випадки повторно перевіряються,
допомагають відсіву, але не замінюють повного гейта для наступника. Це кандидат
реалізації, що потребує незалежного рев'ю. Пошук довільних інваріантів,
універсальне переписування Python й мережа агентів поки не реалізовані.

Кельвінівське охолодження — майбутнє зобов'язання щодо стабільності
обраного контракту, не гарантія безпомилковості реалізації. Зараз 32K
лишається рухомою чернеткою; номер білда відокремлений від температури.
Рівень x0 залишається порожнім резервом для майбутніх генераторів параметрів.

Напрям: пакет переносить достатньо світу, щоб новий учасник міг його
зрозуміти, заперечити й продовжити. Право запропонувати зміну не видається
власником; її допустимість визначається відтворюваним контрактом.

Build 17 робить наступний вузький крок: пакет приймає гіпотези про сталий
результат, незалежність від входу та монотонність. Каталог пропонує 2+2N таких
гіпотез, а перевіряч заново обчислює повну таблицю і повертає встановлену
властивість, контрприклад або незавершеність; збій перевіряча має окремий статус.
Модель у чаті копіює parent і називає властивість — обчислених полів немає.
Це скінченні властивості булевої функції, не загальний синтез інваріантів циклу.
Вони поки не стають новими обмеженнями світу автоматично і не змінюють допуск.

Build 18 додає переносну історію: початковий світ і послідовні пропозиції.
Наступний учасник обирає кореневий ID, повторює кожен перехід і сам відбудовує
поточний світ. Збережений вердикт, ключ автора чи його сервер не є умовою
перевірки. Це дозволяє передати продовження роботи, а не лише окремий результат.
Історія ще не означає єдиної чи найновішої гілки, реальної хронології або
оптимального результату; кілька допустимих продовжень можуть співіснувати.

Build 19 додає явний світ із властивостями. Його наступник може змінювати відповіді,
якщо батько й кандидат задовольняють усі властивості кореня. Режим еквівалентності
лишається типовим; новий режим обирають явно. Наприклад, AND може стати OR при
збереженні неспадності та відповідей на 00 і 11. Це вже зміна поведінки всередині
заданих меж. Властивості не може послабити пропозиція; їх змінюють лише вибором
іншого кореня. Слабкий контракт може допустити небажану або тривіальну програму —
перевіряч не вгадує намірів, яких у властивостях немає.

Build 20 adds a bounded local step toward resumable experiments: an owned Python
lab continuation keeps completed rows across calls without repeating their work.
Session row quotas are separate from the world's per-program ATP ceiling. This
supports both equivalence and inherited-property contracts. It does not transfer
verified progress between chats or processes: imported results still require
recomputation or a separately specified proof mechanism. Mid-row persistence,
state-machine reachability and composition of worlds remain future work.

Build 21 makes that work request portable: a task carries the world, candidate
and claimed prefix between processes or chats. The recipient anchors both world
and candidate, recomputes all imported rows, then advances locally. The packet
opens a common experiment without giving its sender authority over the outcome.
This is asynchronous exchange of a reproducible task, not yet transfer of a
cheaply verifiable proof of computation. Repeated handoffs repeat prefix work;
inspection, hashes and a sender's claimed results do not waive that cost.

Build 22 introduces a first finite temporal experiment: synchronous Boolean
machines with explicit initial states, universally quantified Boolean events and
a safety invariant over reachable states. The checker returns a fully closed
reachable graph, a concrete shortest violating trace, or incomplete; each
expression still passes SKI and an independent Boolean oracle. This makes
counterexamples paths through behavior, not merely single input rows. It does
not yet admit machine replacements, persist traversal progress, express liveness,
or compose independently developed machines. Those require their own contracts.


Build 23 admits changes to the transition rules of those finite machines. The
initial states, event domain and invariant are inherited exactly; both parent
and candidate must establish safety, including states reached only by the new
rules. This lets a proposal change behavior over time without granting its author
permission to weaken the safety question. The gate provides an independently
recomputable admission edge, not a machine-history protocol or a proof that the
chosen invariant captures everything the recipient cares about.


Build 24 closes a small mutation loop for finite machines: propose a transition
rule, obtain a violating event sequence, reuse it to screen further proposals,
and pass surviving proposals through complete safety admission. An imported
counterexample is executable evidence, not authority: its original failure is
recomputed, and only events transfer to another candidate. The pinned checker
still decides admission independently of the search heuristic. This is a finite
local experiment, not autonomous integration or open-ended program synthesis.


Build 25 adds reachable-state observation to those machines. One complete graph
supports discovery of constant bits, bit equalities and implications, with shortest
paths refuting false hypotheses. A participant may submit a property claim without
supplying computed evidence; the recipient recomputes it, including offline. The
observation can cross violations of the machine's declared invariant without
changing that invariant or admitting a new machine. This keeps finding a property,
checking it, and adopting it as a contract as three separate actions.


Build 28 adds an inherited existential reachability obligation: a finite machine
may name states that must remain reachable. This closes one concrete loophole in
safety-only mutation, where a candidate freezes all state and becomes vacuously
safe. Complete graph exploration establishes reachability or absence; a stopped
exploration establishes neither. The obligation is intentionally weaker than
liveness: a possible useful path need not be taken. Transition mutations cannot
remove goals, and observations do not silently adopt new ones.


Build 29 adds a first shared world with two synchronous components. A proposal
may alter one component while inheriting interfaces, wiring and the joint safety
and reachability contract. The checker explores the product rather than trusting
local success: a component that is acceptable alone may break its neighbor. An
independent original-rule comparison holds the wiring/translation boundary before
SKI checking. This is deliberately finite and has one clock; it does not yet offer
assume/guarantee proofs, asynchronous composition or a society of agents. It makes
component-level experimentation possible under explicit obligations to the whole.

## Досліджувати зміну перевіряча, не призначаючи її суддею

Build 30 додає перший вузький експеримент над реалізаціями: два знімки
Boolean-компілятора, переносний корпус і окремо закріплений контролер. Кожний
вхід корпусу перебирається повністю; контролер перевіряє Boolean-відповіді обох
реалізацій власним оракулом. Згода двох реалізацій зі спільною помилкою не є
успіхом, якщо оракул цю помилку бачить. Витрати й терми лишаються спостереженнями,
які повідомляє досліджуваний код, а не незалежно доведеними властивостями.

Інший учасник може додати випадок, що спростовує попередню оцінку на ширшому
корпусі. Старий звіт зберігає свій обсяг; новий корпус і експеримент отримують
інші ідентичності. Запуск відтворюється звичайним Python із незалежно отриманими
ідентичностями контролера та стартового скрипта. Вкладений Python виконується
явно, з правами оператора; цей механізм не є пісочницею.

Це ще не runtime lineage: результат експерименту не змінює закріплений runtime
світу і не дає кандидатові права перевіряти наступного кандидата. Перший профіль
охоплює Boolean-компіляцію; підписані допуски, автомати й композиції потребують
власних явно визначених спостережень. Контролер, його мова й межі доказу самі
залишаються предметом незалежної перевірки.

Build 31 adds a separate proof-data path for finite Boolean machines. A producer
supplies an inductive safe state set and concrete goal paths; a smaller pinned
checker recomputes closure, invariants and paths without loading the producer,
compiler, SKI evaluator or machine-search implementation. This establishes the
finite model's obligations without certifying how the producer worked. A safe
superset of reachable states is sufficient for induction, but membership alone
never establishes a goal's reachability. The recipient anchors the model separately
from any runtime or ATP budget. Python and this small checker remain trusted; its
own correctness is not established by the certificate it checks.

Certified model changes now connect participant-supplied proof data to a successor:
the parent is anchored, protected contract fields remain fixed, and a small checker
rechecks both inductive proofs before returning the candidate certificate. This
allows a different transition system while keeping safety and existential goals.
It does not establish refinement, efficiency or runtime correctness.
