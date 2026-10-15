# Asqueel DB Manager decisioni e ripartenza

> Nota storica: le sezioni su branch, PR aperte, pin sorgente e release descrivono il precedente passaggio di consegne. Le PR sono state successivamente integrate e i pacchetti pubblicati. Per le decisioni di prodotto aggiornate, inclusa la revisione dei profili di connessione persistenti, vedere [Funzionalità previste](feature-previste.md).

Aggiornamento del 12 ottobre 2026. Il progetto nasce dall’analisi di Asqueel e del suo migratore. La prima implementazione è già disponibile nel branch `feat/kajenn-dbmanager`, con una PR aperta: il lavoro nella nuova chat parte dalla revisione di questo codice, non da un repository vuoto.

## Decisioni concordate con il proprietario

Il nome scelto è **asqueel-dbmanager**, al posto di asqueel-migration-server: il servizio deve occuparsi anche di backup, ripristino e utilità amministrative. Il repository appartiene ad **asqueel-org** ed è **pubblico**, con autorizzazione esplicita del proprietario.

Il manager è un’applicazione **Kajenn**. OpenAPI e MCP devono derivare dalle stesse route e dalle funzionalità del framework, senza implementazioni parallele dei protocolli. Kajenn è una dipendenza obbligatoria del manager; il motore di migrazione rimane utilizzabile autonomamente.

La separazione delle responsabilità è:

| Componente | Responsabilità |
| --- | --- |
| `asqueel` | Modello applicativo e accesso ai dati |
| `asqueel-migration` | Validazione dello schema, confronto, generazione SQL ed esecuzione delle migrazioni |
| `asqueel-dbmanager` | Applicazione Kajenn, richieste amministrative, migrazioni tramite il motore, backup, ripristino e utilità |

Le dipendenze vanno dal manager verso Kajenn e il migratore. Asqueel può continuare a usare direttamente il migratore, senza passare dal servizio. La logica SQL di migrazione non deve essere duplicata nel manager; backup e ripristino appartengono al manager e alle sue implementazioni specifiche per database.

Per lo schema in ingresso si accettano entrambi i formati concordati:

- Documento JSON serializzato: deserializzazione interna.
- Dizionario Python: copia profonda.

Il chiamante conserva un input invariato. Il migratore mantiene una sorgente privata e prepara una copia di lavoro nuova a ogni elaborazione, così i filtri del backend non eliminano informazioni per le elaborazioni successive.

## Origine del problema e correzione nel motore

`applyCapabilities()` rimuove dalla struttura desiderata gli elementi che l’adapter non gestisce, evitando differenze permanenti impossibili da applicare. Prima modificava i dizionari condivisi con il chiamante: usare lo stesso input prima con SQLite e poi con PostgreSQL poteva perdere commenti, vincoli o altre informazioni. Ripetere la preparazione poteva inoltre far sparire gli avvisi.

La PR del motore introduce `SqlMigrator(db, structure=...)`, con validazione e isolamento dell’input. L’assegnazione preesistente `migrator.ormStructure = desired` resta disponibile ma copia il valore. La proprietà restituisce la struttura di lavoro: modificarla direttamente non aggiorna la sorgente privata; per cambiare lo schema desiderato occorre riassegnarlo. Questa variazione del contratto è documentata per la versione 0.2.

Il motore espone inoltre `plan_migration()` e `apply_migration()`. Il piano contiene SQL, avvisi, operazioni non supportate e un identificativo; l’applicazione ricalcola il piano, ne verifica l’identificativo e controlla le differenze residue dopo l’esecuzione. La connessione rimane di proprietà del chiamante di queste funzioni.

## Prima implementazione disponibile

Le scelte seguenti descrivono il codice realizzato per la prima versione. Sono il punto di partenza da revisionare, non vincoli immutabili per le future estensioni.

- Python 3.11 o superiore; `asqueel-migration[validation]>=0.2.0,<0.3.0`, Kajenn 0.1 e dipendenza diretta da genro-routes.
- PostgreSQL come primo backend; il motore conserva i propri altri backend.
- Accesso da client locali. L’apertura remota con autenticazione e autorizzazione non è implementata.
- JSON normalizzato come formato principale; XML supportato indicando `format="xml"`. Il JSON semplificato dei produttori deve essere compilato nel formato normalizzato.
- Un migratore e connessioni dedicate per ogni operazione, con chiusura delle connessioni.
- Route pubbliche condivise tra REST e MCP, comprese le operazioni di modifica. Questa scelta supera la vecchia app editor, che esponeva `apply` soltanto via REST.
- Task nativi Kajenn per backup e ripristino lunghi; nessuna coda autonoma del manager.

| Route REST e tool MCP | Operazione |
| --- | --- |
| `check_connection` | Connessione, versione PostgreSQL e capability del migratore |
| `introspect` | Lettura dello schema in JSON normalizzato |
| `plan` | Piano, SQL, avvisi e identificativo |
| `apply` | Esecuzione del piano esaminato e verifica finale |
| `backup` | Archivio PostgreSQL e metadati |
| `backups` | Elenco degli archivi completati |
| `verify_backup` | Verifica checksum e leggibilità dell’archivio |
| `restore` | Ripristino in un database esistente e vuoto |
| `submit` | Invio di backup o ripristino ai task Kajenn |
| `job` | Stato ed esito di un task |

REST usa POST con corpo JSON. Swagger è in `/_meta/docs`, lo schema OpenAPI in `/_meta/schema_json` e MCP in `/mcp`. La proposta iniziale di URL `/v1/...` non è stata adottata in questa implementazione: le route sono direttamente alla radice.

## Migrazioni e concorrenza

`apply` richiede `expected_plan`, ottenuto da `plan`. Le operazioni non supportate bloccano l’esecuzione; le rimozioni sono disabilitate per impostazione predefinita. Un piano cambiato viene rifiutato prima dell’esecuzione.

Il manager usa un advisory lock PostgreSQL nel database di manutenzione `postgres` per serializzare le proprie migrazioni, i backup e i ripristini sulla stessa destinazione. L’account deve poter accedere a quel database. Il lock è cooperativo e non impedisce modifiche DDL eseguite da programmi esterni che non lo rispettano.

La creazione del database resta separata dalla transazione DDL, secondo il contratto del migratore. `verified: false` segnala differenze residue dopo l’applicazione; non significa che le operazioni già eseguite siano state annullate.

## Backup e ripristino

Il manager usa i programmi nativi `pg_dump` e `pg_restore`, che devono essere presenti sul server in una versione compatibile. Produce archivi custom con ID generati dal servizio, metadati, dimensione, data, checksum SHA-256 e versione dello strumento. Un’esportazione dello schema non viene presentata come backup dei dati.

Il ripristino richiede un database già esistente e vuoto e `confirm_database` uguale al nome della destinazione. Usa una singola transazione e non ripristina proprietari o privilegi. Non sovrascrive un’applicazione esistente, non ricrea i ruoli del cluster e non offre point-in-time recovery.

`ASQUEEL_DBMANAGER_BACKUP_DIR` configura gli archivi. `ASQUEEL_DBMANAGER_CONNECTIONS` indica un file JSON con profili di connessione nominati per i task. Nella coda Kajenn entrano il nome del profilo e l’impronta della destinazione, non le password. Una variazione della destinazione invalida il task; la rotazione della password resta consentita.

Lo stato dei task è quello del ciclo di vita Kajenn; non viene simulata una percentuale di avanzamento. Cancellazione, retry e retention automatica degli archivi sono ancora da progettare. La verifica dell’archivio controlla integrità e leggibilità: la prova più forte resta un ripristino reale con verifica dei dati.

## Repository e PR coordinate

Al controllo del 12 ottobre 2026, tutte e tre le PR risultano aperte. La CI era interamente verde al termine dell’implementazione; ricontrollare gli head prima di merge o release.

| Repository e PR | Branch | Commit verificato |
| --- | --- | --- |
| [DB Manager PR 1](https://github.com/asqueel-org/asqueel-dbmanager/pull/1) | `feat/kajenn-dbmanager` | `2192d8a9448512ce47df2dda0a1f6bfcc8423aaf` |
| [Migratore PR 18](https://github.com/asqueel-org/asqueel-migration/pull/18) | `feat/dbmanager-extraction` | `a74f71b99c2b082f081f78c1671fd466cadc2d23` |
| [Asqueel PR 10](https://github.com/asqueel-org/asqueel/pull/10) | `chore/dbmanager-migration-compatibility` | `92466b90bb854cd897db5b0ff0bb327f8df9782b` |

Il `main` iniziale del manager contiene soltanto la base del repository; l’implementazione è nel branch della PR. Non confondere il contenuto del branch locale con una release già pubblicata.

La PR del migratore prepara la versione 0.2.0, rimuove `EditorApp` e l’extra `app`, ma conserva gli helper Python XML. La PR Asqueel amplia il vincolo a `>=0.1.2,<0.3` e aggiorna il pin sorgente nei requisiti di sviluppo. Il manager e Asqueel fissano in CI il commit del motore sopra indicato, in attesa della release. Nessun merge o pubblicazione dei pacchetti è stato effettuato in questo lavoro.

## Verifiche eseguite

- Migratore: pre-push con 399 test superati e 5 saltati, inclusi PostgreSQL, SQLite, MySQL e SQL Server.
- Asqueel: 868 test superati e 1 saltato, incluse integrazioni PostgreSQL contro il nuovo motore.
- DB Manager: 13 test superati, inclusi migrazione reale, REST e MCP, schemi generati, esecuzione task Kajenn, piani superati, lock concorrenti, pulizia di archivi incompleti e protezione delle credenziali.
- Backup e ripristino verificati su database temporanei, confrontando anche righe contenenti apostrofi e caratteri Unicode.
- Ruff, build wheel/sdist e controlli del pacchetto del motore superati.
- Wheel installate in un ambiente pulito, `pip check` senza conflitti e 13 test del manager ripetuti sull’installato.
- Avvio reale del comando installato: OpenAPI disponibile e 10 tool MCP esposti.
- Mypy del motore mantiene 12 segnalazioni preesistenti non bloccanti; non descrivere il controllo dei tipi come interamente pulito.

## Come ripartire nella nuova chat

1. Leggere questo documento, il README, `src/asqueel_dbmanager/app.py`, `operations.py`, `backups.py` e i test. Continuare l’analisi già richiesta sul codice esistente.
2. Verificare branch, modifiche locali, stato e commenti delle tre PR. Correggere eventuali rilievi con test pertinenti, evitando una seconda implementazione dei protocolli Kajenn.
3. Preparare il merge coordinato: il motore deve essere disponibile prima della pubblicazione del manager; Asqueel deve accettare la nuova versione. L’autorizzazione a creare il repository pubblico non equivale a un ordine di pubblicare release o unire tutte le PR.
4. Dopo la release 0.2 del motore, sostituire dove opportuno i pin sorgente temporanei con dipendenze pubblicate e verificare l’installazione documentata.
5. Concordare la priorità delle estensioni: accesso remoto autenticato, ulteriori backend, retention, gestione avanzata dei task e nuove utilità amministrative. Non sono già implementate.

Per lo sviluppo locale, dal checkout del manager, usare un ambiente virtuale dedicato:

```bash
python -m pip install -e '../asqueel-migration[postgresql,validation]'
python -m pip install -e '.[dev,postgresql]'
ruff check src tests
pytest -q
asqueel-dbmanager --port 8000
```

I checkout usati sono `/Users/gporcari/Sviluppo/asqueel/asqueel-dbmanager`, `/Users/gporcari/Sviluppo/asqueel/asqueel-migration` e `/Users/gporcari/Sviluppo/asqueel/asqueel`. L’ambiente temporaneo di verifica delle wheel è `/tmp/asqueel-dbmanager-wheel-env`; è ricreabile e non costituisce una dipendenza del progetto.

Questo documento è stato aggiunto localmente dopo i commit sopra indicati per il passaggio di contesto. Non è incluso nel commit verificato della PR del manager; potrà essere versionato durante il seguito del lavoro.

## Altri rilievi dell’analisi iniziale

Il baco del quoting SQL era già stato corretto e unito con [PR migratore 17](https://github.com/asqueel-org/asqueel-migration/pull/17), chiudendo l’issue 16. Il baco di mutazione dell’input è affrontato dalla PR 18. L’allocazione quadratica dei parametri nelle clausole `IN` di Asqueel era un ulteriore rilievo, rimasto fuori dal lavoro sul manager: non considerarlo risolto né includerlo automaticamente in questo progetto.
