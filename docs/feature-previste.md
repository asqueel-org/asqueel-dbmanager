# DB Manager — funzionalità previste e decisioni

Aggiornato il 13 ottobre 2026 sulla base della discussione con il proprietario.
Questo documento raccoglie le decisioni di prodotto; non attesta che le estensioni
siano già implementate. È il riferimento aggiornato per la progettazione futura.
La guida pubblica descrive la versione disponibile; le note di ripartenza
conservano anche informazioni storiche ormai superate.

## 1. Ruolo e confini

**Decisione:** DB Manager è un servizio condiviso. Gli applicativi lo utilizzano
via REST, gli agenti via MCP. Operazioni e regole devono essere comuni ai due
canali, usando le route e i protocolli Kajenn. È prevista una pagina HTML
dedicata alla revisione della registrazione, della Database Guide e delle regole
di privacy (sezione 14), come primo passo della pagina operativa in Gramlot
(sezione 15). REST e MCP restano utilizzabili anche senza questa interfaccia.

**Decisione:** il manager è un punto di accesso a librerie e strumenti esistenti.
Orchestra autenticazione/autorizzazione, contesto, esiti e integrazioni;
non reimplementa compilatori SQL, motori di migrazione, backup fisico o replay WAL.

**Perimetro attuale:** app importabile in un server Kajenn esistente, server
avviabile dalla CLI e operazioni dirette REST/MCP. I job sono esclusi per ora:
il relativo contratto Kajenn deve essere definito prima di riprendere il lavoro
su accodamento, worker, polling e ripresa. Il codice dei job già presente resta
invariato; l'esclusione dal piano non implica che le route siano state rimosse
o disabilitate.

| Componente | Responsabilità |
| --- | --- |
| Kajenn | Identità, infrastruttura dei tag e route REST/MCP; contratto dei task rinviato |
| Genro Builders / Graphviz | Proposta di renderer generico opzionale per source e gerarchie Bag; issue builders #55 |
| Asqueel | Source delle operazioni, rendering della chiamata, compilazione SQL e runtime dati |
| Asqueel Migration | Lettura/normalizzazione degli schemi e migrazioni |
| Strumenti di backup esistenti | Produzione/ripristino degli archivi, gestione fisica e WAL secondo il backend |
| DB Manager | Accesso autorizzato alle funzionalità, cataloghi, cache, orchestrazione e risposte comuni |

## 2. Utenti e database accessibili

**Decisione:** ogni utente può accedere a N database autorizzati, identificati
logicamente, per esempio `alfa`. Database autorizzato e database effettivamente
raggiungibile sono condizioni distinte.

Kajenn rappresenta il chiamante con un Avatar e tag; le route possono dichiarare
`auth_rule`. Rimane da scegliere chi assegna i tag nell'installazione e dove
risiedono le regole utente/tag → database → operazioni. Il client non può
attribuirsi identità o permessi tramite semplici argomenti della richiesta.

Da definire: distinzione tra applicativo che agisce come servizio e applicativo
che agisce per un utente; delega agli agenti; eventuale tenant; permessi separati
per schema, lettura dati, scritture, migrazione, backup, restore e archivi.
Il permesso di raggiungere una route non concede automaticamente accesso a tutte
le destinazioni. Per operazioni fisiche sul cluster serve un ambito autorizzativo
più ampio del singolo database.

## 3. Connessioni transitorie

**Decisione aggiornata del 13 ottobre:** per le sessioni di interrogazione sono
ammessi profili di connessione persistenti, esclusivamente cifrati, nella cartella
`~/.kajen-dbmanager/db/`. La chiave principale viene custodita in **1Password**;
sul disco resta soltanto il suo riferimento. Questo requisito supera il divieto
precedente di conservare connessioni per questo specifico catalogo.

Le operazioni dirette già esistenti continuano ad accettare la connessione per
richiesta. Le connessioni attive rimangono transitorie anche per i profili: si
decifra il documento per l'operazione e si chiude la connessione al termine.
Credenziali e stringhe di connessione non devono finire in cache LLM, query salvate,
source, archivi di metadati, log, errori, telemetria o spool persistenti dei job.
La connessione posseduta dall'operazione viene rilasciata al termine.

Da progettare nel perimetro attuale: verifica della corrispondenza tra connessione
fornita e database autorizzato e gestione delle credenziali durante la chiamata
diretta, compresa la loro scadenza.

**Rinviato con i job:** trasporto dei segreti al worker senza persistenza,
durata in memoria e comportamento al riavvio. L'implementazione attuale dei job
legge profili da un file sul server e non soddisfa il nuovo contratto transitorio.
Andrà riesaminata quando i job rientreranno nel perimetro; non è un requisito
della prima consegna attuale e non si promette una ripresa automatica.

## 4. Schema persistente con cache

**Decisione:** alla prima necessità DB Manager legge lo schema tramite il
migratore e lo salva. Le query successive sul database `alfa` vengono costruite
sulla struttura memorizzata. La cache ha una durata predefinita configurabile;
il valore concreto non è ancora deciso.

Il contratto da progettare comprende identificativo del database, dialetto,
versione del formato, data di lettura, scadenza e impronta dello schema.
La ricostruzione del modello Asqueel deve preservare quanto serve alla
compilazione. Etichette e significati applicativi possono arricchire lo schema
fisico: la Database Guide conserva provenienza e conferme, con un’estensione
Genropy legacy per i metadati applicativi e gli aiuti dei package (sezione 14).

Per prima lettura e aggiornamento serve una connessione fornita dal chiamante
o recuperata dal profilo cifrato autorizzato.
Senza credenziali disponibili non si promette un aggiornamento autonomo alla
scadenza: va richiesto il refresh, oppure segnalato esplicitamente l'uso di una
copia scaduta, se la politica scelta lo permette.

Proposte da completare: refresh esplicito, invalidazione dopo migrazioni,
ri-validazione delle query salvate quando cambia lo schema e viste del catalogo
coerenti con i permessi. La cache non autorizza l'accesso ai dati.

## 5. Source, compilazione e tre risultati possibili

**Decisione:** le operazioni Asqueel devono poter partire da una `source` che
esprime come si costruisce l'operazione. Da questa derivano i risultati richiesti:

| Risultato richiesto | Risposta e necessità della connessione |
| --- | --- |
| Chiamata Asqueel | Source renderizzata della chiamata, leggibile e riutilizzabile; nessuna connessione se il modello è disponibile |
| SQL | Testo SQL compilato e parametri separati, con dialetto e convenzione di binding; nessuna connessione se il modello è disponibile |
| Risultati | Esecuzione esplicita con connessione fornita per la richiesta e non persistita |

La source dell'operazione e il codice Python renderizzato sono livelli distinti:
formato pubblico e nomi delle API sono ancora da progettare. Preparazione,
compilazione ed esecuzione restano operazioni distinguibili; produrre una query
non deve eseguirla implicitamente.

Il contratto riguarda letture e scritture, preservando policy e contesto.
Le operazioni applicative con hook o più istruzioni non vanno presentate come
equivalenti al solo SQL esportato. Occorre esplicitare i limiti del rendering.

**Dipendenza aperta:** [Asqueel issue #11](https://github.com/asqueel-org/asqueel/issues/11),
creata per il contratto source → chiamata Asqueel / SQL e parametri → esecuzione.
Asqueel ha già piani intermedi e compilazione separata dalla connessione;
la source uniforme non è ancora disponibile come contratto pubblico completo.

## 6. Linguaggio naturale

**Prima implementazione:** SQL e parametri usando la struttura fisica letta
da Migration: tabelle, colonne, tipi, chiavi e relazioni, senza `name_long` o
arricchimenti applicativi. **Nuova decisione di prodotto:** aggiungere Database
Guide, lookup condivisibili e `database_stats`, con revisione alla registrazione
e un’estensione Genropy legacy (sezione 14). Questo supera il precedente limite
al solo database fisico per gli sviluppi futuri, non descrive capacità già
implementate. La source Asqueel resta un obiettivo successivo; restituire
assunzioni e chiarimenti quando necessari.

Esempio: «Clienti che hanno comprato in febbraio ma non in marzo». Anno,
significato di acquisto e trattamento di resi/annullamenti devono essere noti
oppure richiesti; la compilazione non verifica la correttezza di queste scelte.

**Sessione di interrogazione:** l'utente seleziona un database autorizzato tramite
MCP e apre una sessione di durata esplicita, per esempio due ore. Le domande
successive riutilizzano quel contesto mediante un identificativo di sessione;
la stessa funzionalità deve essere disponibile via REST. Esempio: «Usando
DBManager su test_invoice_pg, dimmi quali stati ci sono», seguito da altre
domande senza ripetere la selezione del database.

**Strategia concordata per il provider Anthropic:** struttura completa delle
tabelle autorizzate in un prefisso stabile, domanda e data dopo il blocco
cacheabile; cache di un'ora e warmup dopo circa 50 minuti dall'ultimo utilizzo
riuscito, solo finché la sessione è attiva. Ogni domanda reale può sostituire il
warmup. Chiusura e scadenza interrompono i richiami; la cache del provider scade
naturalmente. Non è una cache dei risultati né una connessione DB mantenuta aperta.
Il timer di sessione è un requisito specifico da progettare nel server; non
reintroduce code, worker o il sistema generale dei job Kajenn.

Sonnet 5.5 con effort medio è il riferimento sperimentale; provider e modello
devono restare configurabili. Il percorso in due passaggi (catalogo, poi sole
tabelle selezionate) resta un'alternativa per strutture troppo grandi. La
generazione SQL e l'esecuzione devono restare distinguibili: chiedere quali stati
sono presenti richiede leggere dati, non dedurli dai nomi delle colonne.

**Implementazione locale del 13 ottobre:** catalogo cifrato genro-storage con
chiave 1Password, CLI `db init-key/add/list`, tool REST/MCP `databases`,
`open_query_session`, `ask_query`, `query_session`, `close_query_session`.
Sessioni in memoria in un processo, durata predefinita 120 minuti, cache provider
un'ora e rinnovo dopo 50 minuti; output SQL oppure risultati in sola lettura.
**Decisione successiva:** niente SQLGlot nel flusso query. PostgreSQL verifica
l'SQL quando vengono richiesti risultati; gli errori correggibili tornano a Sonnet
con la query fallita e un diagnostico depurato, per massimo due correzioni.
Timeout, permessi e connessione non avviano il ciclo. Solo SQL significa proposta
non verificata sul database. Restano transazione read-only, singola istruzione
preparata e limiti di tempo/righe; i privilegi PostgreSQL governano anche le funzioni.
Permessi per identità sul singolo profilo e restrizione localhost conservata;
autorizzazione fine per righe/colonne e distribuzione su più processi restano da
progettare. Lo snapshot viene riletto all'apertura, senza cache persistente della
struttura né invalidazione automatica su DDL esterno. Guida operativa in
[Query sessions](guide/queries.md). Decisioni e vincoli sono dettagliati in
[Query in linguaggio naturale](query-linguaggio-naturale.md).

## 7. Backup logico, restore e S3

**Priorità confermata:** la prima fase dell'area backup riguarda i singoli
database PostgreSQL, con backup logico e relativo ripristino tramite
`pg_dump`/`pg_restore`. Include l'integrazione delle due modalità S3 concordate
e il contratto delle connessioni transitorie. Backup fisici di cluster,
archiviazione continua WAL e PITR appartengono a una fase successiva.
Le operazioni della prima fase sono dirette, senza job; durata delle richieste
e limiti dei trasferimenti devono essere espliciti nel contratto operativo.

La base disponibile usa `pg_dump`/`pg_restore` per PostgreSQL: archivi custom,
metadati e checksum, elenco e verifica, restore in un database esistente e vuoto,
job Kajenn (esistenti ma fuori dal perimetro attuale). Non implementa ancora S3
o recupero tramite WAL.

**Decisione:** supportare entrambe le modalità S3.

| Modalità | Contratto previsto |
| --- | --- |
| S3 gestito dal servizio | Repository/bucket configurato, accesso dello storage tramite identità del servizio e catalogo degli archivi autorizzati |
| S3 fornito dal chiamante | URL firmati temporanei per upload/download di oggetti specifici, senza conservare credenziali del chiamante |

La configurazione di accesso allo storage è distinta dalle connessioni ai
database. Metodo di autenticazione del servizio, provider S3 compatibili e
perimetro dei permessi restano da definire.

Flusso previsto: connessione sorgente transitoria → archivio → trasferimento S3
→ riferimento e metadati; per il restore: riferimento/permesso di lettura S3 →
verifica archivio → connessione destinazione transitoria → ripristino.
Si possono conservare bucket/key, eventuale versione oggetto e checksum;
non URL firmati o segreti. Il catalogo deve distinguere trasferimenti incompleti
da archivi disponibili e rispettare l'autorizzazione del chiamante.

Gli URL firmati S3 concedono accesso temporaneo a specifiche operazioni/oggetti;
scadenza e rinnovo devono essere gestiti per trasferimenti lunghi. Non concedono
implicitamente elenco, cancellazione o accesso all'intero bucket.
Fonte: [AWS — URL firmati](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html).

Proposte discusse, **non ancora selezionate come requisiti**: backup selettivi,
retention, pianificazione, multipart, cifratura aggiuntiva, clonazione,
anonimizzazione, backup pre-migrazione e prove periodiche di ripristino.

## 8. Utility PostgreSQL WAL e ripristino a un istante

**Obiettivo futuro confermato, fuori dalla prima fase backup:** offrire recovery
WAL/PITR e recupero di un singolo database a un istante tramite un ambiente
temporaneo. Non è richiesto implementare queste capacità nel primo intervento.

**Decisione architetturale confermata:** per queste utility DB Manager resta
un punto di accesso a librerie/strumenti esistenti. La scelta del backend,
le operazioni da esporre e il deployment devono ancora essere concordati.

### Prerequisiti e ambito

Il recupero a un istante (PITR) richiede un backup fisico di base e una sequenza
continua dei WAL necessari. Un archivio `pg_dump` non può fungere da base per
il replay WAL. Il recupero fisico riguarda il cluster PostgreSQL, non il solo
DB logico `alfa`; configurazioni e dipendenze esterne vanno considerate a parte.
Fonte: [PostgreSQL — continuous archiving](https://www.postgresql.org/docs/current/continuous-archiving.html).

`pg_basebackup` permette di acquisire una base fisica; richiede accesso e
permessi di replica appropriati. Non installa da solo un sistema continuativo
di archiviazione. Fonte: [PostgreSQL — pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html).

Il restore fisico richiede gestione dei file e dell'avvio del cluster di
recupero: la sola connection string di una normale sessione SQL non basta.
Vanno verificati accesso all'host/ambiente di recovery e compatibilità delle
versioni; per servizi PostgreSQL gestiti si usano le capacità del provider.

### Recuperare un singolo database a un istante

**Obiettivo concordato:** orchestrare il recupero del database `alfa` a un
istante richiesto senza riportare indietro gli altri database della destinazione:

1. Ripristinare una base fisica in un cluster temporaneo isolato.
2. Applicare i WAL fino all'istante richiesto, verificando l'esito del recovery.
3. Esportare il solo database `alfa` tramite `pg_dump`.
4. Ripristinare l'archivio logico nella destinazione esplicitamente scelta.

La procedura richiede risorse e gestione del ciclo di vita dell'ambiente
temporaneo, permessi a livello cluster e controlli sulla destinazione finale.
Non implica la sovrascrittura automatica di un database esistente.
Le eventuali ottimizzazioni di restore selettivo del backend restano soggette
ai suoi limiti e non equivalgono a un PITR del singolo database dentro un
cluster attivo. Riferimento: [pgBackRest — restore selettivo](https://pgbackrest.org/user-guide.html#restore/option-db-include).

### Backend candidato

**Proposta:** valutare un adapter per pgBackRest, che offre backup completi,
differenziali/incrementali, archiviazione WAL, retention, PITR e repository S3.
DB Manager traduce le richieste autorizzate nelle operazioni del backend e ne
normalizza stato ed esito. Installazione e configurazione del motore restano
esplicite. Fonte: [pgBackRest — guida ufficiale](https://pgbackrest.org/user-guide.html).

Non è stata scelta una dipendenza definitiva. La preferenza del proprietario
è riusare implementazioni esistenti, siano esse librerie o strumenti esterni.

### Utility candidate

| Utility | Risultato previsto |
| --- | --- |
| Diagnosi configurazione | Prerequisiti mancanti, backend disponibile, accesso al repository e identità del cluster |
| Stato archiviazione | Ultimo WAL archiviato, errori, ritardo e indicatori di accumulo |
| Avvio backup fisico | Job sul backend con tipo supportato e riferimento al backup prodotto |
| Catalogo recovery | Basi disponibili, timeline e copertura WAL verificata, con eventuali lacune dichiarate |
| Preparazione PITR | Piano per un istante richiesto: base, WAL necessari, compatibilità e destinazione isolata |
| Esecuzione restore | Operazione amministrativa esplicita tramite il backend, su destinazione controllata |
| Prova di recupero | Ripristino isolato con controlli concordati e registrazione dell'esito |
| Retention | Uso delle regole del backend, preservando le dipendenze tra basi e WAL |

PostgreSQL espone statistiche dell'archiver tramite `pg_stat_archiver`:
sono utili alla diagnosi, ma non provano da sole che tutta la catena conservata
sia recuperabile. Fonte: [PostgreSQL — statistiche](https://www.postgresql.org/docs/current/monitoring-stats.html).

Per basi prodotte da `pg_basebackup`, `pg_verifybackup` verifica il manifest
secondo il proprio contratto; non sostituisce una prova reale di recovery.
Per archivi di altri backend si usano le rispettive verifiche.
Fonte: [PostgreSQL — pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html).

### Continuità, credenziali e S3

L'archiviazione WAL deve continuare anche quando nessun utente sta effettuando
richieste. Proposta coerente con la non persistenza delle connection string:
il motore installato nell'infrastruttura database mantiene il processo continuo
e la propria identità di servizio; DB Manager conserva solo i riferimenti
operativi consentiti e ne espone i controlli. La forma di delega e i segreti
infrastrutturali richiesti dal backend sono una decisione di deployment ancora
aperta, non un'eccezione implicita al contratto delle connessioni transitorie.

Le due modalità S3 sono confermate per gli archivi logici, ma non si presume
che un backend WAL accetti URL firmati per oggetto. Un singolo URL temporaneo
non copre una sequenza futura di WAL: occorre accesso rinnovabile al repository
o un'integrazione specifica, da verificare. Il supporto S3 del backend non
implica supporto alla modalità URL firmati del manager.

Le cancellazioni S3 non devono interrompere le catene necessarie al recupero:
la retention fisica va coordinata dal motore competente. Non promettere un
istante recuperabile dal solo elenco degli oggetti o dalla data dell'ultimo WAL.

## 9. Stato e prossime decisioni

| Area | Stato |
| --- | --- |
| Migrazioni, introspezione e backup logico locale | Esistenti; da confrontare con i nuovi contratti |
| Job asincroni e worker | Esistenti ma esclusi per ora; attendere la definizione del contratto Kajenn |
| REST per applicativi e MCP per agenti | Direzione confermata; infrastruttura già presente |
| N database per utente e schema persistente con cache | Requisiti confermati; autorizzazioni, formato e TTL da progettare |
| Connessione fornita dal chiamante e non persistita | Requisito confermato per le operazioni dirette; adeguamento dei job rinviato |
| Source e tre output | Requisito confermato; dipendenza Asqueel issue #11 |
| Backup/restore del singolo database e S3 nelle due modalità | Priorità della prima fase backup; adeguamento delle connessioni e integrazione S3 da implementare |
| Diagrammi da JSON Migration | Implementazione locale SVG/DOT; integrazione generica opzionale proposta in builders #55 |
| Capability `graphviz` | Implementata localmente: `capabilities` via Python, CLI, REST/MCP verifica il runtime e dichiara i formati disponibili |
| App montata su server Kajenn esistente | Operazioni dirette verificate sotto `/dbmanager`, insieme a un'app alla radice e senza worker |
| Utility WAL/PITR tramite motori esistenti | Obiettivo futuro confermato, fuori dalla prima fase; backend da scegliere |
| Recupero del singolo DB a un istante tramite cluster temporaneo | Obiettivo futuro confermato: recovery fisico isolato, estrazione logica e restore nella destinazione scelta |
| Sessioni di interrogazione REST/MCP e cache LLM | Implementate localmente: catalogo cifrato, struttura completa, TTL un'ora, warmup, SQL e letture limitate; singolo processo locale |
| Modello AI interno e/o agente esterno | Sperimentato provider Anthropic diretto; progettare integrazione delle sessioni e possibilità di generazione affidata all'agente |
| Registrazione guidata e Database Guide | Prima pagina HTML e guida manuale cifrata implementate localmente; analisi Sonnet e domande automatiche successive |
| Estensione Genropy legacy | Decisa, da implementare: aiuti dei package, metadati applicativi e override di istanza |
| Privacy per tabella/colonna e analisi dei risultati | Default e override persistiti dalla pagina; encoder/decoder futuri, nessun valore `C`, risultati mai inviati al modello nella beta |
| Lookup e `database_stats` | Decisi, da implementare: valori condivisibili, statistiche datate e query di aggiornamento conservate |
| Pagina operativa Gramlot | Prima beta HTML con iframe e servizi reali implementata localmente; sezioni 15–16 |
| Altri backend DB e ulteriori utility | Non ancora selezionati |

Per il primo intervento sui backup, confrontare le operazioni logiche esistenti
con il contratto delle connessioni transitorie e le due modalità S3, tramite
operazioni dirette. I job sono sospesi e non bloccano questa consegna.
La scelta del backend WAL è rinviata alla fase successiva. Restano da approfondire
anche assegnazione dei permessi Kajenn e ciclo di vita della cache dello schema.
Le implementazioni locali successive all'analisi iniziale sono indicate nella
sezione 11; la proposta condivisa con builders è descritta nella sezione 12.

## 10. Confronto con il codice e proposta per la prima versione

Analisi del checkout `52791f1` (versione del pacchetto `0.1.0`), effettuata il
12 ottobre 2026. «Presente» indica una capacità osservata nel codice; non implica
che soddisfi già il contratto del futuro servizio condiviso.

La prima consegna proposta è **backup/restore logico PostgreSQL utilizzabile da
applicativi e agenti autorizzati, con connessioni transitorie e le due modalità
S3, tramite operazioni dirette e senza job**. La priorità sui backup di singolo
database è confermata. Rimandare anche
cache e query a una consegna distinta è una proposta di perimetro, non una nuova
decisione del proprietario: questi obiettivi restano validi. «Prima versione»
indica qui questa nuova consegna, non la `0.1.0` già pubblicata.

### Funzionalità previste ed esistenti

| Area prevista | Evidenza attuale | Differenza da colmare |
| --- | --- | --- |
| REST e MCP comuni | 10 operazioni esposte dallo stesso albero Kajenn, con OpenAPI | Conservare la parità anche per autorizzazioni e nuovi contratti |
| Servizio condiviso con utenti | Accesso limitato a localhost; nessuna regola per utente nelle route | Integrare identità Kajenn e autorizzazioni prima dell'esposizione remota |
| N database autorizzati per utente | Le richieste dirette ricevono parametri di connessione; nessun catalogo logico o grant | Catalogo senza segreti, associazione identità/tag → DB → operazioni e verifica della destinazione |
| Connessione transitoria | Chiamate dirette con `connection: dict`, connessioni rilasciate e password escluse dagli errori pubblici | Definire/supportare la connection string concordata e trasferimenti senza persistere segreti; job rinviati |
| Lettura dello schema | `introspect` tramite Asqueel Migration | Aggiungere persistenza, versione, TTL e refresh per la cache concordata |
| Migrazioni | `plan`/`apply`, verifica del piano, controllo post-apply e lock | Integrare autorizzazioni; invalidazione della cache quando questa verrà introdotta |
| Source → chiamata Asqueel / SQL / risultati | Nessuna operazione corrispondente nel manager | Contratto Asqueel issue #11 e integrazione nel servizio; il SQL di `plan` è SQL di migrazione, non un servizio query |
| Linguaggio naturale | Nessuna integrazione | Decidere ruolo del modello/agente e sviluppare il flusso sullo schema memorizzato |
| Backup di singolo DB | `pg_dump` custom, ID, metadati, SHA-256 e controllo con `pg_restore --list` | Associare archivio a DB logico e permessi; aggiungere destinazioni S3 |
| Restore di singolo DB | Verifica archivio, conferma del nome, DB esistente e vuoto; restore in una transazione | Aggiungere provenienza S3 e controlli separati su archivio e destinazione |
| Catalogo e verifica archivi | Elenco locale completo e verifica per ID | Filtrare per autorizzazioni, registrare riferimenti remoti e distinguere trasferimenti incompleti da archivi disponibili |
| S3 del servizio | Assente | Adapter storage, configurazione del repository e credenziali infrastrutturali, upload/download e verifica |
| S3 tramite URL firmati | Assente | Trasferimento per oggetto, scadenza/errori e riferimenti persistibili senza salvare URL firmati |
| Job e stato | Task Kajenn e polling; proprietario fisso `dbmanager-local`, profili letti da file | Fuori dal perimetro attuale; proprietà, autorizzazioni e segreti al worker da riesaminare dopo la definizione Kajenn |
| WAL/PITR | Assente | Fase successiva già concordata, compreso recupero del singolo DB attraverso cluster temporaneo |

Riferimenti nel repository: [route e job](../src/asqueel_dbmanager/app.py),
[operazioni e connessioni](../src/asqueel_dbmanager/operations.py),
[archivi e restore](../src/asqueel_dbmanager/backups.py),
[limiti di deployment](guide/deployment.md), [test](../tests/).

Verifica della base esistente: **28 test superati** il 12 ottobre 2026, usando
il codice del checkout e un PostgreSQL temporaneo locale. La prima esecuzione
usava Asqueel Migration `0.2.0`; la suite è stata poi rieseguita con **`0.2.1`**,
ultima release verificata su PyPI e corrispondente al commit `3681b0d` del motore,
con tutti i 28 test superati. La `0.2.1` corregge validazione degli input e uso
del database della connessione per la creazione; non aggiunge le funzionalità
indicate come mancanti nella tabella. Il vincolo del manager al momento dell'analisi
(`>=0.2.0,<0.3.0`) ammette già questa release, ma non la richiede come minimo.
I test coprono anche
migrazioni reali, backup/restore con dati Unicode, archivio corrotto,
destinazioni non vuote e lock. I test dei job usano un backup simulato;
questa suite non dimostra capacità multiutente, S3 o query ancora assenti.

### Lavori necessari per la consegna proposta

1. **Identità e autorizzazioni.** Stabilire chi assegna i tag Kajenn e dove sono
   conservati i grant. Introdurre ID logici dei DB, associazione alle destinazioni
   consentite e permessi per backup, restore ed elenco/verifica archivi.
   I controlli devono valere anche conoscendo un ID appartenente a un altro utente,
   e coprire le route di migrazione/introspezione se esposte nello stesso servizio.
2. **Connessioni transitorie nelle operazioni dirette.** Definire/supportare il
   formato della connection string, verificare la destinazione autorizzata e
   rilasciare le risorse al termine. Non persistere segreti o URL firmati.
   Definire limiti di durata e comportamento in caso di scadenza/interruzione;
   nessuna ripresa tramite job è prevista in questa consegna.
3. **Storage e catalogo.** Separare la produzione dell'archivio dal suo deposito,
   riusando `pg_dump`/`pg_restore`. Implementare S3 del servizio e URL firmati per
   upload/download, riferimenti e checksum, stati dei trasferimenti e pulizia dei
   file temporanei. Decidere provider compatibili e dimensioni/durate supportate;
   multipart rimane opzionale finché tali limiti non lo rendano necessario.
4. **Restore completo da S3.** Recuperare l'archivio autorizzato, verificarne
   integrità e provenienza consentita, autorizzare separatamente la destinazione
   e applicare i controlli già presenti. Proposta per questa consegna: mantenere
   destinazione esistente e vuota, senza introdurre sovrascrittura o creazione DB.
5. **Verifiche e documentazione.** Esercitare i flussi REST/MCP con più identità,
   backup → S3 → restore e confronto dei dati, guasti di trasferimento,
   checksum errato, URL scaduto e interruzioni delle operazioni dirette. Aggiornare
   API, esempi, configurazione e manuale per il nuovo contratto. Indicare i job
   esistenti come esclusi da questa evoluzione; la loro revisione resta sospesa.

Prima di implementare servono quindi soprattutto tre scelte: autorità dei
permessi Kajenn, contratto operativo delle chiamate dirette e configurazione S3.
Non serve scegliere un motore WAL per questa consegna. La cache dello schema e
la source Asqueel non sono prerequisiti tecnici del backup logico.

### Criterio di completamento proposto

Un utente autorizzato su `alfa` può, tramite REST o MCP, fornire una connessione
transitoria, eseguire il backup e riceverne l'esito. L'archivio viene salvato nella
modalità S3 scelta; un chiamante autorizzato può ripristinarlo in una destinazione
vuota esplicitamente confermata e ritrovare i dati. Le due modalità S3 sono
verificate separatamente. Un utente privo dei permessi necessari non può leggere
metadati/esiti né usare archivio o destinazione. Connessioni e URL firmati
non risultano nei file persistenti, log o risposte di errore; fallimenti e
interruzioni non producono un archivio dichiarato disponibile per errore.

Il restore mantiene i limiti correnti: non ricostruisce ownership/grant o ruoli
del cluster. Il lock coordina le operazioni DB Manager, non gli altri client che
eseguono DDL. Questi limiti vanno mantenuti espliciti nel manuale.

Se invece la prima versione deve includere **tutto il flusso query concordato**,
ai lavori sopra vanno aggiunti cache/versionamento dello schema, integrazione
della source Asqueel e dei tre output, e la scelta del flusso linguaggio naturale.
È un perimetro più ampio, con una dipendenza esterna esplicita nell'issue #11.

## 11. Diagrammi da JSON Migration — implementazione locale

**Nuova priorità richiesta:** generare subito un diagramma a partire dal JSON
normalizzato Migration, anche dalla CLI e senza connessione al database.

Implementata nel checkout, non ancora pubblicata: funzione Python `diagram`,
omonima route REST/tool MCP e comando `asqueel-dbmanager diagram schema.json
-o schema.svg`. L'adattatore riusa la validazione Migration e Graphviz per
layout/rendering SVG; l'esportazione DOT funziona senza Graphviz installato.
Mostra tabelle, colonne, tipi, PK/FK e relazioni anche composte, tra schemi o
verso la stessa tabella. Non deduce cardinalità applicative.

La CLI conserva l'avvio del server preesistente. La nuova implementazione
richiede Migration `>=0.2.1,<0.3.0` per includere le correzioni della validazione.
Guida, limiti ed esempio scaricabile: [Diagrammi](guide/diagrams.md).

Il CLI accetta anche `diagram -g INSTANCE` / `--genropy INSTANCE`, in alternativa
al JSON. Il resolver Genropy carica la configurazione dell'istanza; Migration
legge la struttura reale PostgreSQL e il renderer produce DOT/SVG. La connessione
resta in memoria, senza avviare GnrApp né applicare migrazioni. Sono supportati
il database principale, i riferimenti a variabili d'ambiente e l'override
`GNR_DB_DSN` (URL senza query/fragment); store remoti e tunnel automatici restano
esclusi. Genropy deve essere disponibile nello stesso ambiente Python. Nessuna
cache viene ancora utilizzata e questa risoluzione per nome è limitata al CLI.

Lo stesso selettore `-g/--genropy` è disponibile anche nei comandi CLI
`introspect` e `backup`. Il primo esporta JSON Migration su stdout o file
(`-o`, senza sovrascrittura), con filtro `--schema` ripetibile. Il secondo usa
il BackupStore esistente in modo sincrono, con `--backup-dir` opzionale e
metadati JSON su stdout. Nessun job o profilo di connessione persistente viene
creato. Guida: [CLI](guide/cli.md).

Disponibile anche `publish_diagram` via REST/MCP: genera uno snapshot SVG
persistente e restituisce URL per pagina HTML (zoom, adattamento alla larghezza,
download) e file SVG. I link rispettano il mount dell'app e l'accesso resta
limitato a localhost. Il CLI accetta `diagram ... --server-url URL` e stampa
l'URL completo. Gli snapshot risiedono in `ASQUEEL_DBMANAGER_DIAGRAM_DIR`
(default `.dbmanager/diagrams`), senza credenziali; nessuna scadenza automatica.

Filtri dei diagrammi implementati per Python, CLI, REST/MCP e pubblicazione HTML:
schemi (`schemas` / `--schema`), tabelle (`tables` / `--table`) e grappolo
(`cluster` / `--cluster`). Ascendenti e discendenti seguono le FK in traversate
separate; `relatives` seleziona il verso e `depth` limita i salti. Cicli gestiti;
i filtri combinati si intersecano e le relazioni con estremità escluse non vengono
disegnate. Le pagine pubblicate restano snapshot fissi, senza filtri interattivi
o trascinamento delle singole tabelle nella vista attuale.

Esperimento aggiunto senza sostituire Graphviz: `publish_diagram(renderer="cytoscape")`
e CLI `--renderer cytoscape --server-url ...`. Cytoscape.js 3.34.3 è incluso
localmente con licenza MIT. Il viewer usa il medesimo filtro di struttura, con
layout autonomo senza Graphviz, tabelle trascinabili, porte sulle colonne, dettagli,
filtri interattivi entro lo snapshot, export PNG e posizioni salvabili nel browser.
I vecchi snapshot e l'export DOT/SVG restano operativi. Nessuna modifica ai database;
salvataggio delle posizioni limitato al browser, senza condivisione server.

Verifica locale: `test_invoice_pg` produce un SVG con 75 tabelle e 57 relazioni;
88 test passati, incluso backup CLI e ripristino su database temporaneo; Ruff
e build Sphinx superati. Corretta anche l'introspezione
senza filtro: DB Manager scopre gli schemi accessibili non di sistema e passa
l'elenco a Migration, che altrimenti restituisce una struttura vuota.

Verifiche: 47 test superati con Migration 0.2.1, Graphviz e PostgreSQL reali;
Ruff, build Sphinx con warning come errori, wheel/sdist e comando CLI del wheel
installato verificati. Graphviz è ora installato nell'ambiente locale di lavoro;
nelle altre installazioni serve il programma `dot` solo per produrre SVG.

## 12. Graphviz come renderer opzionale dei builders

**Decisione:** proporre in genro-builders un `GraphvizRenderer` riutilizzabile
per source dei builders e gerarchie Bag, con dipendenza opzionale. Issue aperta:
[genro-builders #55 — Optional Graphviz renderer](https://github.com/genro-org/genro-builders/issues/55).
È una proposta di progettazione: API, dipendenza Python e implementazione nei
builders non sono ancora definite o disponibili.

La separazione concordata è:

- `structure`: struttura del database in JSON Migration, input di DB Manager.
- `diagram`: operazione che genera il diagramma.
- `graphviz`: capability che abilita l'output `svg` quando integrazione e runtime
  necessari sono disponibili. Non usare `schema` come nome della capability,
  per evitare la sovrapposizione con SQL schema.

Graphviz è il pacchetto nativo e contiene il programma `dot`. DOT è anche il
formato testuale che descrive nodi e collegamenti. Nel flusso attuale l'SVG è
prodotto da `dot`; non esiste un secondo motore che generi SVG senza Graphviz.
Una volta generato, l'SVG si visualizza senza Graphviz sul client.

Valutare un extra Python, per esempio `genro-builders[graphviz]`, soltanto se
serve un wrapper Python: installarlo con pip non installa automaticamente il
programma nativo `dot`. Import, rilevamento della disponibilità ed errori devono
lasciare utilizzabili i builders e gli altri renderer senza Graphviz.
L'attuale esportazione DOT di DB Manager resta possibile senza runtime nativo.

L'integrazione generica appartiene ai builders; DB Manager mantiene l'adattatore
specifico per tabelle, colonne e foreign key. Il renderer potrà essere riusato
per gerarchie, dipendenze e workflow. L'esistente `SvgRenderer` dei builders
emette elementi SVG dichiarati; `GraphvizRenderer` aggiungerebbe il layout
automatico di nodi e collegamenti. L'API illustrativa
`builder.render(mode="graphviz", format="svg")` rimane da concordare nell'issue.

**Stato in DB Manager:** l'adattatore locale della sezione 11 funziona già;
la capability `graphviz` è ora esposta come descritto nella sezione 13. L'adozione
del futuro renderer dei builders resta da integrare dopo la definizione della
sua API. Questa decisione non reintroduce i job nel perimetro e non cambia il
rinvio di WAL/PITR.

## 13. Capability Graphviz e montaggio dell'app — implementazione locale

L'operazione `capabilities`, disponibile come route REST/tool MCP e comando
`asqueel-dbmanager capabilities`, restituisce per esempio:

```json
{
  "capabilities": {"graphviz": true},
  "diagram_formats": ["dot", "svg"]
}
```

Il controllo esegue un piccolo rendering locale con timeout di due secondi e
verifica che l'output sia SVG valido. Se Graphviz manca, non funziona o supera
il timeout, dichiara `graphviz: false` e solo il formato `dot`. Non legge il DB,
non espone percorsi/diagnostica del processo e non conserva il risultato tra
chiamate. È una disponibilità tecnica al momento della richiesta, non un
permesso né una garanzia che ogni successivo rendering riesca. Una richiesta
SVG non disponibile fallisce esplicitamente; non viene convertita in DOT.
Il rilevamento CLI riguarda l'ambiente locale, quello REST/MCP il server.

La composizione Kajenn esistente permette di registrare
`(DbManagerApp, {"code": "database_admin", "mount": "dbmanager"})` accanto ad
altre app. Sono verificate discovery, Swagger, chiamate dirette REST/MCP e
controlli di accesso locale sotto `/dbmanager`; l'app alla radice resta separata.
Non serve registrare `DbManagerWorker` per le operazioni dirette e importare
l'app non avvia un altro server. Il server standalone avviabile dalla CLI resta
disponibile con il comando esistente.

I job non sono stati modificati: le route legacy rimangono dichiarate e non
sono parte della composizione verificata. Il limite del worker che cerca l'app
alla radice non è stato corretto, in accordo con l'esclusione dei job dal
perimetro. Guida: [montaggio dell'app](guide/installation.md#mount-in-an-existing-kajenn-server)
e [capability Graphviz](guide/diagrams.md#discover-graphviz-support).

Verifiche di questa integrazione: **62 test superati**, inclusi Graphviz e
PostgreSQL reali, scenari senza renderer e composizione con app alla radice;
Ruff, build Sphinx rigorosa, CLI `capabilities` e link locali verificati.
Le modifiche restano locali e non ancora pubblicate.


## 14. Registrazione guidata, Database Guide e contesto dei dati

**Decisioni del 13 ottobre 2026.** Il flusso descritto qui estende il catalogo
cifrato e le sessioni di interrogazione. La prima implementazione locale della
pagina di revisione e della guida manuale persistente è descritta nella sezione
16; analisi automatica, encoder/decoder dei risultati, lookup nel contesto e
`database_stats` restano da implementare. Queste decisioni non reintroducono
i job Kajenn.

### Registrazione e revisione via HTML

La registrazione di un database avvia la prima analisi della struttura tramite
Migration. Sonnet propone descrizioni di tabelle e colonne, relazioni utili,
convenzioni, lookup candidate e domande su ciò che non può dedurre: per esempio
quale data rappresenti una vendita e come riconoscere fatture definitive,
annullate o cancellate logicamente. Le proposte di privacy si basano inizialmente
su struttura e metadati: non autorizzano a inviare valori riservati al modello.

La registrazione restituisce un **link a una pagina HTML** per completare la
revisione, utilizzabile anche quando il flusso parte da CLI o MCP. La pagina
richiede l’accesso dell’utente autorizzato: possedere il link non basta a ottenere
permessi sul database o sulla configurazione.

La pagina mostra:

- Per ogni tabella: descrizione modificabile, conteggi e default di condivisione
  dei dati, con checkbox esplicita «Condividi i dati con il modello».
- Per ogni colonna: **Eredita / Condividi / Nascondi**, mostrando l’effetto finale.
  Una sola checkbox non rappresenta i tre stati necessari.
- Domande dell’analisi, spiegazioni aggiuntive e indicazioni già confermate.
- Lookup proposte e anteprima dei campi e delle informazioni condivisibili.
- Data di rilevazione delle statistiche e scelta della colonna temporale.

**Conferma e attiva** salva la guida e la policy approvata. La registrazione può
restare in bozza se l’utente rimanda le risposte: resta disponibile la generazione
SQL dalla struttura autorizzata, mentre l’invio dei risultati al modello rimane
disabilitato fino alla conferma delle regole. Gli stessi controlli devono valere
per REST e MCP, non soltanto nell’interfaccia HTML.

Un comando esplicito permette di ripetere l’analisi e aggiornare la guida. La
pagina consente anche modifiche successive; una nuova analisi evidenzia variazioni
e nuove domande, preservando le decisioni dell’utente. Nomi e firme dei comandi
sono ancora da definire: `dbmanager db analyze <database>` è un esempio di
interfaccia prevista, non un comando già disponibile.

### Database Guide e versioni

La **Database Guide** accompagna la struttura fisica con significati di tabelle
e colonne, percorsi di relazione utili, convenzioni applicative, interpretazioni
dei termini e ambiguità da chiarire. Distingue esplicitamente:

- Fatti verificati sulla struttura o tramite letture autorizzate.
- Interpretazioni proposte da Sonnet, non ancora confermate.
- Indicazioni e correzioni confermate dall’utente.

Il documento è leggibile e modificabile; i metadati associati conservano
provenienza, data di analisi, versione della guida e impronta della struttura.
Le correzioni confermate non vengono sovrascritte dalla rigenerazione: se una
modifica strutturale le rende incompatibili, vengono segnalate per revisione.
La guida è consultabile dai chiamanti autorizzati tramite CLI, REST e MCP.

La persistenza della guida evita di ripetere l’analisi semantica a ogni sessione.
È distinta dalla cache del provider: struttura e guida approvata costituiscono
un prefisso stabile riutilizzabile secondo la strategia della sezione 6. Una
sessione mantiene una versione identificata della guida, evitando cambiamenti
silenziosi delle interpretazioni durante la conversazione. Le statistiche hanno
un ciclo di aggiornamento separato; se cambia il contenuto del prefisso, cambia
anche la porzione riutilizzabile nella cache del provider.

### Estensione Genropy legacy e aiuti dei package

DB Manager resta generico; un’estensione dedicata a **Genropy legacy** sfrutta
istanze, package caricati, metadati applicativi e peculiarità del framework.
Un comando dedicato, per esempio `dbmanager db analyze-genropy -g <istanza>`
(sintassi da definire), compone queste informazioni con la struttura reale.

I package riutilizzati da molte applicazioni, per esempio `sys` e `adm`, possono
contenere un **`llm_help.md`** con significati delle tabelle, convenzioni,
relazioni e indicazioni utili ai futuri chiamanti. Markdown è il formato previsto
per gli aiuti curati dai manutentori; JSON per il catalogo generato e i suoi
metadati. L’eventuale alternativa `llm_help.json` e il percorso esatto nei package
restano dettagli di formato da definire, non un requisito di doppia manutenzione.

Si distinguono tre livelli:

1. Aiuto del package, condiviso e versionato insieme al package.
2. Indicazioni dell’applicazione/istanza, che possono precisare o correggere
   quelle generiche senza modificare il package comune.
3. Struttura e dati effettivamente rilevati nel database, con data e provenienza.

Gli aiuti vengono confrontati con la versione installata e la struttura reale.
Un chiarimento specifico di un’istanza viene salvato localmente nella sua guida:
non diventa automaticamente una regola per tutte le applicazioni che usano il
package. Metadati e aiuti possono proporre classificazioni di privacy; la policy
effettiva viene confermata per il database/istanza.

### Privacy: default sulla tabella e override sulle colonne

**Decisione finale:** non si usa più il valore `C` né un codice di sostituzione
per ogni campo. L’attributo `privacy` definisce quali valori possono essere
inviati al modello, con default sulla tabella e override sulle colonne.

| Attributo | Significato |
| --- | --- |
| `privacy="H"` | Hide: escludere il valore dai dati inviati al modello |
| `privacy=None` (`null` in JSON) | Allow: consentire l’invio del valore, entro i permessi del chiamante |
| Attributo assente sulla colonna | Ereditare il default della tabella |
| Attributo assente sulla tabella | Applicare la policy predefinita dell’istanza |

L’attributo esplicito della colonna prevale sul default della tabella. **Assente
e `None` esplicito devono restare distinguibili** in serializzazione ed editing.
La classificazione privacy non concede accesso a dati altrimenti non autorizzati.

Per una tabella riservata si propone `privacy="H"` come default; si condividono
esplicitamente l’ID tecnico e i numeri/date utili all’analisi. Gli altri campi
restano esclusi. Email, indirizzi, telefoni e codici fiscali sono candidati da
nascondere nella prima analisi. Numeri e date non sono automaticamente innocui:
l’utente può mantenere nascosti anche importi, date di nascita o altri valori.
Una lookup condivisibile può invece avere `privacy=None` sulla tabella, con
singole colonne nascoste tramite `H`.

Esempio: `customer` con default `H`; `name` ed `email` senza attributo ereditano
l’esclusione; `id` e `registration_date` con `privacy=None` sono condivisibili.
Le regole vengono da metadati Genropy quando disponibili, oppure dalla
configurazione DB Manager, e sono revisionabili nella pagina HTML.

### Encoder, decoder e analisi successive dei risultati

I due percorsi restano distinti:

1. **Domanda → SQL → risultati per l’utente:** al modello arrivano struttura e
   contesto autorizzato; DB Manager esegue la query e mostra i risultati al
   chiamante autorizzato. Le righe non vengono automaticamente reinviate all’LLM.
2. **Richiesta di elaborazione o grafico sui risultati:** un encoder locale
   applica la policy prima dell’invio. Esclude i campi `H`, conserva solo quelli
   condivisibili e gli ID tecnici consentiti. Il modello produce l’elaborazione
   e un decoder locale risolve i riferimenti per la presentazione all’utente.

Si usano normalmente gli **ID originali**, spesso di 22 caratteri, senza
prefissi; `tabella:id` è un’opzione quando occorre distinguere la provenienza.
Non serve creare una mappa di pseudonimi di sessione quando gli ID tecnici sono
condivisibili. Un ID contenente informazioni riservate non va autorizzato solo
perché è una chiave. Il modello può correlare gli ID condivisi: il flusso non va
presentato come anonimizzazione irreversibile.

La provenienza delle colonne deve essere preservata attraverso join, alias e
campi calcolati: una query non può aggirare `H` rinominando una colonna. La policy
di origine vale anche per valori derivati; la condivisione delle aggregazioni
va dichiarata esplicitamente. Se non si può determinare la provenienza, il valore
non viene inviato come ripiego. Un ID necessario alla presentazione può essere
recuperato solo se ciò non altera la semantica della query, in particolare per
raggruppamenti e aggregazioni.

Il modello restituisce riferimenti strutturati agli ID e specifiche dei grafici;
DB Manager risolve localmente nomi ed etichette per l’utente autorizzato e rende
il grafico. Non si basa su sostituzioni indiscriminate nel testo libero. Il
contesto locale mantiene anche la colonna da risolvere: uno stesso record può
avere nome e descrizione differenti associati allo stesso ID. I campi esclusi
non devono rientrare nei prompt tramite log, diagnostici o cronologia.

### Lookup condivisibili

Stati, condizioni di pagamento, tipi di prodotto e altre lookup approvate
possono essere incluse nel contesto con **codice, descrizione e relazioni**.
La loro utilità è semantica: `QLD → Queensland`, insieme alla relazione
`customer.state → state.code`, aiuta a interpretare «clienti del qsland» e a
usare il codice reale, senza inviare dati identificativi dei clienti.

Una tabella piccola non è automaticamente una lookup né automaticamente
condivisibile. Sonnet propone le candidate e l’utente conferma campi e regole.
La lettura deve avere limiti espliciti e non presentare un elenco troncato come
completo. I valori possono cambiare: conservare data di lettura e versione,
prevedere aggiornamento manuale e una scadenza distinta dalla struttura.
Si applica sempre la policy effettiva alle colonne, anche quando i valori sono
inclusi nella guida o nel prefisso della cache. In caso di ambiguità residua il
modello chiede un chiarimento invece di inventare una corrispondenza.

### `database_stats`: valori, freschezza e query di aggiornamento

**`database_stats` è separato dalla Database Guide:** descrive lo stato dei dati
in un momento preciso, mentre la guida raccoglie significati e regole più
stabili. La pagina di registrazione mostra le statistiche accanto alle
descrizioni, con la data di rilevazione.

Statistiche previste:

- Numero di record per tabella, distinguendo attivi e cancellati logicamente
  quando esiste una convenzione verificata.
- Per tabelle di movimenti: data minima/massima e conteggio per anno.
- Numero di record senza data e colonna temporale usata. L’analisi propone la
  colonna, ma l’utente può cambiarla: data fattura, creazione e pagamento hanno
  significati diversi.
- Indicazione se il conteggio è esatto o stimato; per tabelle grandi può essere
  mostrata prima una stima, con calcolo esatto su richiesta.

Ogni statistica conserva almeno:

| Campo | Contenuto |
| --- | --- |
| Valore | Conteggio, intervallo o distribuzione rilevata |
| `computed_at` | Data dell’ultimo calcolo riuscito |
| `max_age` | Durata massima per considerare il valore fresco |
| `sql`, `params` | Query e parametri approvati da rieseguire |
| Versione della struttura | Struttura a cui si riferisce la query |
| Metadati | Tabella, campo temporale, filtri, criterio attivi/cancellati, esatto/stimato e policy di condivisione |

**All’inizio di un’analisi**, DB Manager controlla le statistiche necessarie:
riutilizza quelle fresche ed esegue le query conservate per quelle mancanti o
scadute, con credenziali autorizzate, sola lettura e limiti operativi. Poi prepara
il contesto da fornire al modello. Non serve far ricostruire a Sonnet le query
approvate a ogni richiesta. La freschezza non dipende da un job in background.

Quando cambia la struttura, le query interessate vengono rivalidate. Se un
aggiornamento fallisce o non c’è una connessione disponibile, il valore precedente
mantiene la sua data e viene indicato come non aggiornato; non viene presentato
come una misura corrente. Restano da definire TTL predefiniti, limiti di costo e
formato pubblico, configurabili secondo l’installazione.

Le statistiche aiutano a riconoscere la copertura temporale: se i dati si fermano
al 2025, una domanda sugli ultimi tre mesi del 2026 può essere spiegata senza
cambiare silenziosamente il periodo richiesto. La visibilità nella pagina non
ne autorizza automaticamente l’invio al modello: anche aggregati e conteggi
seguono una policy esplicita di condivisione.


## 15. Pagina operativa Gramlot e beta test progressivo

**Direzione concordata:** realizzare una pagina di uso di DB Manager in Gramlot,
partendo dalla registrazione e revisione della sezione 14. Gramlot è in sviluppo
attivo e cambierà rapidamente nei prossimi giorni: DB Manager sarà anche un
**beta test applicativo**, utile a scoprire cosa funziona, cosa manca e cosa
richiede correzioni nel framework.

**Prima fase:** pagine semplici con soli elementi HTML, form nativi, checkbox,
select, textarea e tabelle HTML, utilizzando le capacità del core disponibili e
verificate al momento dell’integrazione. Non si attende l’arrivo dei componenti
avanzati per iniziare. Le scelte di privacy conservano i tre stati
Eredita / Condividi / Nascondi anche con controlli HTML ordinari.

**Evoluzione:** adottare progressivamente i Gramlot components quando saranno
introdotti nel core. La POC è il riferimento delle possibilità future: contiene,
tra gli altri, esempi di griglie modificabili, controlli, alberi e chartBox con
Bag e selezione condivise tra griglia e grafico. Per DB Manager questo suggerisce
future viste di revisione dei metadati, risultati navigabili e grafici collegati.
La direzione indicata dal proprietario è trasferire progressivamente in Gramlot
le capacità della POC e aggiungerne altre; non si assume una data di disponibilità
né la compatibilità delle vecchie API con quelle future.

La POC resta materiale di studio e sperimentazione, **non una dipendenza runtime
né il contratto corrente del core**. Non si copiano in blocco i suoi componenti
in DB Manager. Ogni adozione si verifica sul Gramlot effettivamente utilizzato,
conservando il comportamento delle pagine già realizzate.

Gramlot gestisce presentazione e interazione; operazioni, autorizzazioni, policy
privacy e persistenza restano in DB Manager e sono comuni ai chiamanti REST/MCP.
L’adattatore Kajenn di `gramlot-py-server` è una base di integrazione presente nel
checkout consultato: montaggio con DB Manager e passaggio dell’identità devono
ancora essere verificati concretamente. Il diagramma Graphviz/Cytoscape esistente
rimane riutilizzabile, senza vincolare la prima pagina a una sua riscrittura.

Per ogni problema del beta test conservare versione/commit di Gramlot, esempio
minimo riproducibile, comportamento atteso e osservato, distinguendo difetti di
DB Manager da limiti o regressioni di Gramlot. Gli aggiornamenti del framework
richiedono una verifica dei flussi effettivamente usati: apertura pagina,
binding, modifica dei campi, salvataggio e autorizzazioni. Il beta test produce
feedback concreto senza trasformare API sperimentali in promesse di stabilità.

Riferimenti consultati nel workspace: `gramlot-poc/README.md`,
`gramlot-poc/docs/examples/chartbox/README.md`,
`gramlot-poc/docs/examples/grid-editor/README.md` e
`gramlot-poc/docs/source/guide/components.rst`. Descrivono esperimenti della POC,
non funzionalità già integrate in DB Manager.


## 16. Prima impalcatura Gramlot — implementazione locale del 13 ottobre

È disponibile una prima pagina `/ui/` (o `/dbmanager/ui/` con quel mount), con
navigazione HTML laterale e pagine in iframe sulla stessa origine. Le pagine
aperte restano montate durante la navigazione. Dipendenza opzionale `ui`, Gramlot
core 0.2.16 fissato per questa prova; nessun componente avanzato della POC.

Funzioni collegate ai servizi reali:

- Registrazione di database e importazione della connessione principale di
  istanze Genropy legacy, con verifica connessione e catalogo cifrato.
- Lettura della struttura, anteprima del piano e applicazione di una migrazione
  dopo conferma esplicita; backup logico e restore su destinazione vuota.
- Arruolamento AI manuale: struttura letta da Migration, descrizioni, default H
  sulle tabelle e override Eredita / Condividi / Nascondi sulle colonne.
- Salvataggio cifrato della guida come bozza o approvata, revisioni contro
  sovrascritture concorrenti e controllo della versione della struttura.
- Chat su un profilo arruolato, con SQL o risultati, dettaglio dei parametri,
  assunzioni e uso della cache; spiegazioni approvate nel contesto del modello.

Il servizio `console_action` è comune a REST e MCP. La modalità `local` accetta
solo loopback e rifiuta origini browser estranee. La modalità esplicita `kajenn`
richiede l’identità dell’host, senza fallback locale; i profili hanno allowlist
per identità e il tag `dbmanager_admin` abilita registrazione e operazioni
amministrative. In questa prima integrazione la superficie MCP completa e le
API legacy richiedono quel tag in modalità Kajenn; gli utenti dei profili possono
usare le funzioni del workbench tramite REST. Non è stato aggiunto un login.

**Limiti deliberati:** niente analisi iniziale Sonnet, aiuti dei package,
lookup caricate, `database_stats`, encoder/decoder di risultati o grafici AI.
Le regole privacy sono persistite, ma nessuna riga dei risultati viene inviata
al modello in questa versione. La chat web richiede l’arruolamento; il percorso
API precedente resta utilizzabile con sola struttura per profili privi di guida
approvata. La registrazione Genropy importa la connessione primaria, non un
catalogo completo di package e store. La lista backup web comprende gli archivi
attribuiti ai profili tramite il workbench.

**Riscontro del beta test:** `gramlot-py-server` 0.2.7 richiede Kajenn >=0.4.1,
incompatibile con la dipendenza Kajenn <0.2 di DB Manager. Un piccolo bridge ASGI
isolato ospita quindi `GramlotFileServer` nel server esistente, senza aggiornare
Kajenn né importare la POC. Il bridge è sostituibile con l’adattatore standard
quando sarà affrontato l’aggiornamento del server.

Prova nel browser: struttura reale di `test_invoice_pg` (76 tabelle), arruolamento
con default H e domanda sugli stati: otto risultati reali, 2,398 secondi per la
chiamata al modello, nessuna correzione SQL e cache utilizzata. La sessione di
prova è stata chiusa. Guida operativa: [Gramlot workbench](guide/workbench.md).

**14 ottobre 2026 — diagramma nel workbench:** aggiunta la pagina
`Operations / Database diagram`. Il database registrato viene letto tramite
Migration e mostrato nell'iframe con il viewer Cytoscape esistente e disposizione
iniziale Graphviz, quando disponibile. Restano zoom, trascinamento e filtri;
un pannello per tabella mostra chiave primaria, indici e vincoli. Non richiede
arruolamento AI. Gli snapshot controllano identità e versione del profilo anche
nei download e consentono l'incorporamento solo dalla stessa origine.
