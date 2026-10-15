# Query da linguaggio naturale nel DBManager

> Aggiornamento del 13 ottobre 2026: le decisioni sulle sessioni MCP e sulla cache del provider sono riportate qui e in [Funzionalità previste](feature-previste.md). La prima integrazione prevista genera SQL dal solo database fisico; la preferenza Asqueel e gli arricchimenti descritti nel riepilogo originario sotto restano obiettivi successivi. Il contratto source è tracciato in [Asqueel issue #11](https://github.com/asqueel-org/asqueel/issues/11).

## Decisioni del 13 ottobre: sessioni REST/MCP e cache LLM

Stato aggiornato: implementazione locale delle sessioni e del catalogo cifrato,
con CLI e tool REST/MCP. Guida in [Query sessions](guide/queries.md). Gli esperimenti
API iniziali non eseguivano SQL; l'integrazione aggiunge `output=results` con
controllo PostgreSQL, transazione read-only e limiti. La scelta successiva dell'utente
autorizza la persistenza di connessioni cifrate e pone la chiave in 1Password.

**Correzione concordata:** eliminare SQLGlot dal flusso. Il modello propone SQL;
se richiesti risultati, il database lo esegue e fornisce gli errori. Per errori
correggibili il servizio rimanda a Sonnet SQL, parametri e diagnostico depurato
(SQLSTATE, descrizione standard, eventuale posizione), mantenendo il prefisso
cacheabile; massimo due correzioni e tre tentativi complessivi. Permessi,
connessione e timeout fermano l'operazione. Nessun controllo di esistenza di
tabelle/colonne lato Python; output SQL senza esecuzione dichiarato non verificato.
Rimangono i vincoli di lettura lato PostgreSQL e i limiti dell'operazione.

### Esperienza richiesta

L'utente può dire all'agente MCP:

> Usando DBManager su test_invoice_pg, dimmi quali stati ci sono.

L'agente seleziona il database e apre una sessione di interrogazione, con una
durata scelta dall'utente (esempio: due ore). Le richieste successive, come
«e in quali di questi abbiamo clienti?», riutilizzano la sessione. Il database
selezionato è associato al chiamante e alla sessione, mai a una variabile globale
condivisa tra utenti. Una sessione applicativa non dipende dalla persistenza del
trasporto MCP: ogni chiamata successiva passa il suo identificativo.

Contratto implementato:

- `open_query_session(database, duration_minutes)`: autorizza la selezione,
  prepara la struttura e restituisce `session_id`, database e scadenza.
- `ask_query(session_id, question, output)`: propone SQL e parametri oppure,
  se richiesti e autorizzati, restituisce risultati dopo validazione ed esecuzione.
- `close_query_session(session_id)`: chiude il contesto e ferma i richiami.

Sono disponibili anche `databases()` e `query_session(session_id)`. `ask_query`
ha `output="sql"` predefinito e `max_rows=200` (massimo 500). Le route Kajenn
forniscono REST e MCP con le stesse regole. Nel flusso discusso DBManager chiama il
provider configurato; un eventuale percorso in cui genera SQL l'agente MCP resta
distinto e non deve comportare una seconda chiamata LLM obbligatoria.

«Quali stati ci sono» può significare l'anagrafica degli stati oppure gli stati
effettivamente associati ai clienti: esplicitare l'interpretazione o chiedere un
chiarimento quando il contesto non basta. I nomi effettivi si ricavano dai dati;
la struttura non permette di inventare l'elenco né di assumere codici come `QLD`.
La richiesta di risultati deve essere distinta da `output=sql`, che non esegue
la query. Preparazione, validazione ed esecuzione restano passaggi separati anche
quando vengono orchestrati da una sola richiesta MCP.

### Contesto e durata della cache

- Partire dalla struttura Migration completa delle sole tabelle autorizzate,
  senza `name_long`, metadati applicativi o righe del database. SQL e parametri
  sono il primo output previsto; il contratto source Asqueel viene dopo.
- Prefisso stabile con istruzioni e struttura; domanda, data di riferimento e
  contesto delle domande precedenti vengono dopo il blocco cacheabile. Ordinare
  deterministicamente il JSON e non inserire identificativi o date variabili
  nel prefisso. La gestione della cronologia e dei chiarimenti è da progettare.
- Con Anthropic usare un breakpoint esplicito `cache_control` con `ttl: "1h"`.
  Riferimento delle prove: Sonnet 5.5, effort medio; provider/modello configurabili.
- Inizializzare la cache all'apertura, anche tramite `max_tokens: 0`. Dopo circa
  50 minuti dall'ultimo utilizzo riuscito, inviare un warmup con lo stesso modello,
  effort e prefisso se la sessione è ancora attiva. Le domande reali rinnovano la
  cache e spostano il richiamo successivo. Verificare hit e scritture dai contatori
  `usage`, senza assumere che la cache sia sempre disponibile.
- La sessione ha una propria scadenza assoluta: domande e warmup non prolungano
  automaticamente le due ore. Alla chiusura/scadenza fermare i richiami; questo
  non elimina immediatamente la cache del provider, che segue il proprio TTL.
- La cache del provider è distinta dalla persistenza/TTL della struttura in
  DBManager e dalla cronologia conversazionale. Il prefisso va comunque inviato
  a ogni richiesta e continua a occupare il contesto del modello.
- Associare il contesto a database, versione della struttura, perimetro dei
  permessi e modello. Cambiamenti richiedono rivalutazione e ricostruzione; cache
  e identificativo di sessione non sostituiscono l'autorizzazione a ogni operazione.
- Il timer server è limitato alla vita della sessione. Code, worker e job Kajenn
  restano esclusi; gestione di riavvii, più processi e richiami concorrenti va
  definita prima dell'implementazione, senza promettere rinnovi dopo un arresto.

Per circa 31.700 token con Sonnet 5.5, alle tariffe verificate il 13 ottobre 2026:
scrittura 5 minuti circa $0,0793, scrittura un'ora $0,1268, lettura $0,00317 in
entrambi i casi. Due ore senza domande costano circa $0,133 con TTL un'ora e due
warmup, contro $0,162 con TTL 5 minuti e 26 warmup. Stime della sola struttura,
esclusi piccoli input variabili, risposte, imposte ed eventuali cache miss.
Con traffico continuo la durata breve può convenire; per la sessione discussa
si è scelta un'ora per tollerare pause e ridurre i richiami.

Riferimento: [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).
Gli esperimenti sono conservati in `experiments/nl_sql/2026-10-12-queensland/`:
la prova con tutte le 75 tabelle, 788 colonne e 57 relazioni ha usato 31.718 token
input e 618 output, senza cache; il percorso Sonnet in due passaggi ne ha usati
5.970 input e 782 output. Sono singole misurazioni, non un benchmark statistico.

### Accesso ai risultati e verifiche richieste

Generare SQL dalla struttura memorizzata non richiede una connessione aperta.
Introspezione ed esecuzione richiedono invece una connessione transitoria,
rilasciata al termine dell'operazione. La sessione non conserva stringhe di
connessione, password o chiavi del provider nel proprio stato, nei prompt o nei
log. Il chiamante fornisce la connessione per l'operazione oppure il server la
risolve tramite un resolver autorizzato; non deve essere il modello a ricavarla.
La CLI importa la configurazione Genropy con `db add NAME -g INSTANCE` nel
catalogo cifrato; MCP seleziona solo profili registrati, senza passare credenziali
all'agente. I profili consentono una lista esplicita di identità; senza Avatar
resta il chiamante locale fidato. L'autorizzazione fine Kajenn rimane da progettare.

Per il primo percorso di risultati qui proposto, limitare l'esecuzione a letture
con autorizzazioni, timeout e limiti di righe applicati dal servizio/database;
il solo controllo sintattico di una SELECT non basta. Questo è il perimetro
conservativo implementato; usare un ruolo PostgreSQL con privilegi di sola lettura.

Verificare almeno: isolamento fra utenti/sessioni, scadenza assoluta, cancellazione
dei timer, cache hit su domande diverse, ripartenza dopo un miss, cambio struttura
o permessi, nessun segreto persistito, nessuna esecuzione in modalità SQL e
risultati reali per l'esempio degli stati su un dataset controllato.

## Riepilogo originario e obiettivi successivi

Riepilogo del 12 ottobre 2026. Estensione futura di `asqueel-dbmanager`, discussa nella chat di `kajenn-mail-proxy` e riportata qui per proseguire nel progetto corretto. La funzionalità non è ancora implementata.

## Obiettivo espresso dal proprietario

Il DBManager deve poter ricevere attraverso MCP una richiesta di query in linguaggio naturale e sottoporla a un modello, per esempio Sonnet, insieme allo schema del database. Il risultato desiderato è una query Asqueel oppure SQL diretto, pronta per una successiva esecuzione.

La forma Asqueel è preferita. Il modello chiamato deve conoscere chiaramente la grammatica Asqueel supportata, senza doverla dedurre dal solo schema o dalla propria conoscenza generale.

Esempio di richiesta:

> Cercami i clienti che non hanno comprato in marzo ma hanno comprato in febbraio.

La capacità appartiene al DBManager ed è riutilizzabile dalle applicazioni Kajenn. Non fa parte delle due fasi di migrazione del mail proxy.

## Base disponibile nel codice

- `DbManagerApp` in `src/asqueel_dbmanager/app.py` deriva già da `McpOpenApiApplication`: le route pubbliche alimentano REST/OpenAPI e MCP.
- L'operazione `introspect`, implementata in `src/asqueel_dbmanager/operations.py`, restituisce lo schema fisico normalizzato. Non contiene necessariamente il significato applicativo dei dati.
- Asqueel permette di costruire una query e ottenere `query.compiled`, con SQL e parametri, senza eseguirla e senza richiedere una connessione. L'esecuzione avviene con operazioni distinte, come `execute()` o `fetch()`.
- Il manager attuale è orientato a PostgreSQL e chiamanti locali fidati. Il supporto SQLite di Asqueel non implica che il manager supporti già quel backend.

Questi elementi costituiscono la base tecnica; non esiste ancora nel manager un tool di generazione di query da linguaggio naturale.

## Flusso proposto

1. Il chiamante invia domanda, database di destinazione e preferenza di formato.
2. Il DBManager prepara il contesto pertinente: schema, relazioni, significati applicativi, grammatica Asqueel e dialetto SQL.
3. Il modello restituisce una proposta strutturata oppure le domande necessarie per risolvere ambiguità.
4. Il DBManager valida la proposta. Per Asqueel costruisce e compila la query usando la libreria installata.
5. Il chiamante riceve query, parametri, spiegazione, assunzioni e stato della validazione. L'esecuzione richiede un'operazione distinta.

La separazione fra preparazione ed esecuzione è stata confermata nella discussione successiva, insieme ai tre output: chiamata Asqueel renderizzata, SQL con parametri, oppure risultati con connessione transitoria. Nomi e firme dei nuovi tool restano da definire; il tool `plan` esistente riguarda le migrazioni e non va confuso con la preparazione delle query.

## Contesto da fornire al modello

Il contesto deve comprendere:

- Tabelle, colonne, tipi, chiavi e relazioni rilevanti per la domanda.
- Metadati applicativi disponibili: etichette, descrizioni, formule e convenzioni del dominio.
- Versione Asqueel e contratto delle query: riferimenti alle colonne, percorsi delle relazioni, operatori, sottoquery, parametri ed esempi validi.
- Funzionalità realmente implementate e limiti della versione in uso.
- Dialetto SQL della destinazione e perimetro di dati accessibile al chiamante.

La grammatica delle query è distinta dalla grammatica con cui si dichiarano tabelle e connessioni. Fornire soltanto quest'ultima non basta. Il contratto destinato al modello dovrebbe essere versionato insieme ad Asqueel e verificato con esempi compilabili.

L'introspezione fisica va arricchita con le informazioni del modello applicativo quando disponibili. Credenziali e righe del database non sono necessarie al flusso di base; eventuali campioni di dati richiedono una scelta esplicita sul contesto da trasmettere al provider.

## Forma del risultato proposta

Preferire una descrizione strutturata della query, traducibile dal DBManager nelle chiamate Asqueel consentite. Il formato preciso va progettato sulle capacità reali della libreria: non è un formato di serializzazione già disponibile.

La risposta dovrebbe contenere:

- Formato scelto: Asqueel oppure SQL diretto.
- Descrizione strutturata Asqueel e, quando utile, codice Python equivalente da leggere o esportare.
- SQL compilato e parametri separati; per SQL diretto, dialetto dichiarato.
- Spiegazione della selezione, assunzioni e chiarimenti ancora necessari.
- Versione del contratto Asqueel e riferimento allo schema usato.
- Esito e limiti della validazione.

Il DBManager non dovrebbe eseguire Python arbitrario generato dal modello. SQL diretto è un'alternativa richiesta dal chiamante o motivata da un limite di rappresentazione Asqueel, non un ripiego silenzioso dopo un errore.

## Esempio e ambiguità applicative

La domanda sui clienti corrisponde alla logica:

> Esiste almeno un acquisto del cliente in febbraio e non esiste alcun acquisto dello stesso cliente in marzo, nell'anno indicato.

Prima di completare la query occorre conoscere l'anno e cosa significhi “acquisto”: ordine inserito, pagato, spedito o fattura; inoltre, se annullamenti e resi vadano esclusi. Queste informazioni possono provenire dal contesto applicativo o da chiarimenti del chiamante.

I periodi vanno rappresentati con intervalli di date espliciti, preferibilmente con inizio incluso e fine esclusa, tenendo conto del fuso orario quando i campi lo richiedono. La query deve restituire clienti senza duplicarli per ogni acquisto.

La compilazione verifica la rappresentabilità della query, non la correttezza del significato attribuito alla domanda. Non tutti gli errori SQL sono rilevabili senza il database.

## Esecuzione futura e runtime

La prima capacità discussa prepara query; non avvia migrazioni, invii mail o altre azioni conseguenti ai risultati.

Per un'eventuale esecuzione, autorizzazioni, limiti e contesto tenant vanno verificati dal servizio anche se il modello ha prodotto una query plausibile. I filtri del modello Asqueel non sostituiscono l'autorizzazione applicativa, in particolare con SQL diretto.

Il runtime Asqueel attuale è sincrono e mantiene connessioni per thread. In Kajenn, l'intera operazione database deve stare in una route sincrona eseguita nel pool oppure in una singola funzione affidata a `server.run_sync(...)`: contesto, query, commit/rollback e cleanup sul medesimo thread. Non distribuire una transazione fra chiamate separate al pool. La sola compilazione non richiede I/O sul database.

## Decisioni ancora aperte

- Provider e modello configurabili; Sonnet è l'esempio indicato, non una versione o dipendenza già scelta.
- Nomi e firme dei tool per preparazione, validazione ed eventuale esecuzione.
- Formato strutturato delle query e modalità di pubblicazione del contratto Asqueel.
- Provenienza e aggiornamento dei metadati applicativi e selezione dello schema pertinente.
- Gestione dei chiarimenti e criteri per proporre SQL diretto.
- Salvataggio e riuso delle query, con gestione delle variazioni di schema e versione.
- Perimetro dell'esecuzione: una prima versione limitata alle letture è una proposta da confermare.

## Verifiche per la futura implementazione

- Esempio febbraio/marzo su dati noti: clienti in un solo mese, in entrambi, senza acquisti e con più acquisti; confini temporali e anno bisestile.
- Chiarimenti espliciti quando anno o significato dell'acquisto non sono determinabili.
- Query Asqueel compilabile con la versione dichiarata e parametri separati dal testo SQL.
- Rifiuto o diagnosi di tabelle, colonne e costrutti inesistenti o non supportati.
- Nessuna esecuzione durante la preparazione; nessuna esecuzione di Python generato.
- Autorizzazioni e isolamento anche per SQL diretto, se l'esecuzione viene introdotta.
- Coerenza dei risultati e degli errori sui canali REST e MCP.

Questo riepilogo conserva requisiti e proposte della discussione; non autorizza né attesta l'implementazione delle estensioni elencate. Per lo stato del manager e delle migrazioni vedere [Decisioni e ripartenza](decisioni-e-ripartenza.md).
