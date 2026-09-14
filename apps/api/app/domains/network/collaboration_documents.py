"""I documenti che un cliente deve leggere e accettare per diventare Promoter.

The legal text lives here, on the server, and travels to the dashboard
through `GET /network/agents/apply/documents`. It is deliberately NOT written
into a React component:

- it is what people legally sign, so it must be versioned, reviewable in one
  place, and impossible to have two copies of;
- the acceptance record stores the version a person actually saw, which is
  only meaningful if the text and the version number are defined together;
- changing it must not require touching the dashboard at all.

**Adding a document**: append an entry to `COLLABORATION_DOCUMENTS`. The
dashboard renders whatever this list contains, one scrollable panel and one
checkbox per entry, and the backend refuses an application that does not
accept every one of them at its current version. Nothing else changes.

**Changing a document's text**: bump its `version`. Anybody who applies from
then on records the new version; past acceptances keep the version they
actually agreed to. Never edit text without bumping -- that would silently
restate what somebody already signed.
"""

from dataclasses import dataclass, field

# --- Block types the dashboard knows how to render ---------------------------
#
# A small vocabulary rather than raw HTML or Markdown: the text is legal
# content coming from the server and rendered into a customer's browser, so
# it is structured data the UI formats, never markup the UI interprets.

BLOCK_HEADING = "heading"
BLOCK_PARAGRAPH = "paragraph"
BLOCK_CLAUSE = "clause"
BLOCK_BULLETS = "bullets"
BLOCK_TABLE = "table"
BLOCK_SIGNATURE = "signature"


def heading(text: str) -> dict:
    return {"type": BLOCK_HEADING, "text": text}


def paragraph(text: str) -> dict:
    return {"type": BLOCK_PARAGRAPH, "text": text}


def clause(number: str, text: str) -> dict:
    """A numbered contract clause, e.g. ("3.4.", "Il Procacciatore non potra ...")."""
    return {"type": BLOCK_CLAUSE, "number": number, "text": text}


def bullets(*items: str) -> dict:
    return {"type": BLOCK_BULLETS, "items": list(items)}


def table(columns: list[str], rows: list[list[str]], caption: str | None = None) -> dict:
    """Ready for Allegato A (tabella dei compensi) and Allegato B (schema
    avanzamenti di carriera): figures somebody is agreeing to must be readable
    as a table, not buried in a paragraph."""
    return {"type": BLOCK_TABLE, "columns": columns, "rows": rows, "caption": caption}


def signature(text: str) -> dict:
    """The closing declaration of a document -- rendered as a callout so it
    is obvious which text the checkbox below actually covers."""
    return {"type": BLOCK_SIGNATURE, "text": text}


@dataclass(frozen=True)
class CollaborationDocument:
    key: str
    version: str
    title: str
    subtitle: str
    #: The sentence next to the checkbox. Written in the first person and in
    #: the past tense ("Ho letto e accetto...") because that is what is being
    #: recorded -- a declaration, not an instruction.
    acceptance_label: str
    blocks: list[dict] = field(default_factory=list)


# =============================================================================
# 1. Il contratto
# =============================================================================

_CONTRACT_BLOCKS: list[dict] = [
    paragraph(
        "tra LIAL ENERGY (cod. fisc. 13438020011), con sede in Torino, corso "
        "Matteotti n. 30, in persona dell'amministratore unico e legale rappresentante sig. Carlo "
        "Ragazzi (cod. fisc. RGZCRL68L14H355X), P.E.C. lialenergy@pec.it — in seguito, denominata "
        "LIAL"
    ),
    paragraph(
        "e il sig./la società sottoscrittore del presente contratto, i cui dati anagrafici, codice "
        "fiscale/partita IVA, residenza/sede legale e indirizzo P.E.C. risultano dall'anagrafica "
        "registrata sulla piattaforma Lial Energy — in seguito, denominato Procacciatore."
    ),

    heading("1. Premesse"),
    clause(
        "1.1.",
        "È stata costituita, in Torino, la s.r.l. THE LIAL ENERGY [d'ora innanzi semplicemente LIAL], "
        "titolare di un'azienda che svolge attività di procacciamento di affari aventi ad oggetto la "
        "conclusione di contratti relativi o comunque connessi a:",
    ),
    bullets(
        "fornitura di energia elettrica e di gas naturale, anche disgiuntamente;",
        "prodotti di telefonia, offerte sul traffico voce e dati, accessi alla rete telefonica;",
        "prodotti e servizi digitali e per l'industria.",
    ),
    clause(
        "1.2.",
        "È intenzione di LIAL avvalersi di una pluralità di soggetti i quali, senza alcun vincolo di "
        "esclusiva, di continuità e di stabilità, promuovano la conclusione di contratti aventi ad "
        "oggetto i prodotti e servizi di cui al punto 1.1. (d'ora innanzi, i «Prodotti»).",
    ),
    clause(
        "1.3.",
        "Il Procacciatore ritiene di poter reperire terzi interessati ai Prodotti e intende promuovere, "
        "senza alcun vincolo di esclusiva, di continuità e di stabilità, per conto di LIAL, la "
        "conclusione dei citati contratti.",
    ),
    clause(
        "1.4.",
        "A tal fine, egli si impegna ad osservare il contenuto del presente contratto e ogni "
        "disposizione di legge che sia comunque applicabile alla presente fattispecie. In particolare, "
        "il Procacciatore garantisce, ove svolga la propria attività in maniera non occasionale, di "
        "essere iscritto all'apposito albo di cui alla L. 3 febbraio 1989, n. 39.",
    ),

    heading("2. Oggetto del contratto"),
    clause("2.1.", "Le premesse formano parte integrante e sostanziale del presente contratto."),
    clause(
        "2.2.",
        "Il presente contratto ha per oggetto la segnalazione di eventuali affari e la raccolta di "
        "eventuali ordini dei clienti, svolta dal Procacciatore:",
    ),
    bullets(
        "in via del tutto occasionale e secondaria;",
        "in assenza di rapporto di esclusiva, continuità o stabilità;",
        "senza alcun vincolo di subordinazione o para-subordinazione;",
        "al di fuori di qualsiasi relazione contrattuale diversa dal mero coordinamento utile ad "
        "espletare l'attività di raccolta delle ordinazioni dei clienti e la trasmissione degli stessi a LIAL.",
    ),
    clause(
        "2.3.",
        "L'incarico sarà liberamente svolto dal Procacciatore in piena indipendenza e autonomia "
        "operativa, gestionale e organizzativa. Tuttavia, essendo il Procacciatore a conoscenza dei "
        "rapporti in essere tra LIAL e le società che hanno affidato alla medesima lo sviluppo della "
        "propria rete di clienti, ogni segnalazione di affari che si ponga in contrasto con le regole "
        "previste dai menzionati rapporti — che il Procacciatore dichiara di conoscere — non darà luogo "
        "ad alcun compenso, fatto anzi salvo il diritto di LIAL di ottenere il risarcimento di eventuali "
        "danni subiti.",
    ),
    clause(
        "2.4.",
        "Il Procacciatore ha facoltà di avvalersi di collaboratori, sia autonomi che subordinati, "
        "dell'attività dei quali sarà comunque responsabile e le cui spese saranno a suo esclusivo "
        "carico. Il Procacciatore è tenuto a far sì che i propri collaboratori e/o dipendenti rispettino "
        "i medesimi impegni assunti con il presente contratto.",
    ),
    clause(
        "2.5.",
        "LIAL non instaurerà alcun rapporto diretto o indiretto con collaboratori o dipendenti del "
        "Procacciatore. Il Procacciatore si impegna espressamente a tenere indenne LIAL da qualsiasi "
        "azione o pretesa venisse avanzata dai propri dipendenti e/o collaboratori, essendo il "
        "Procacciatore l'unico soggetto obbligato verso i medesimi, per stipendi, compensi, indennità, "
        "versamenti previdenziali e assicurativi e quant'altro previsto dalla vigente normativa in tema "
        "di lavoro autonomo e subordinato.",
    ),
    clause(
        "2.6.",
        "Nello svolgimento dell'incarico il Procacciatore tutelerà prioritariamente gli interessi di "
        "LIAL, ed agirà osservando i più elevati standard di correttezza, diligenza e perizia, ai sensi "
        "dell'art. 1176 c.c.",
    ),
    clause(
        "2.7.",
        "Il Procacciatore si impegna, per sé e i propri collaboratori, a tenere riservata ogni notizia "
        "di cui dovesse eventualmente venire in possesso in forza del presente contratto, fatto salvo il "
        "rispetto di norme imperative che ne autorizzino o impongano la rivelazione, ovvero salva diversa "
        "espressa autorizzazione di LIAL. Gli obblighi di riservatezza avranno efficacia anche dopo la "
        "cessazione del presente rapporto.",
    ),

    heading("3. Modalità di svolgimento del rapporto"),
    clause("3.1.", "Il Procacciatore potrà svolgere la propria attività sull'intero territorio italiano, senza vincoli di zona."),
    clause(
        "3.2.",
        "Le Parti convengono, pertanto, che LIAL si avvarrà anche di altri procacciatori, agenti e/o "
        "collaboratori per la promozione dei Prodotti e si riserva di trattare direttamente con chiunque "
        "la conclusione di contratti relativi all'offerta dei Prodotti.",
    ),
    clause(
        "3.3.",
        "Il Procacciatore e i suoi collaboratori non potranno in alcun modo assumere obbligazioni o "
        "stipulare contratti in nome e per conto di LIAL.",
    ),
    clause(
        "3.4.",
        "Il Procacciatore non potrà offrire garanzie sui Prodotti, servizi aggiuntivi, sconti o modalità "
        "di pagamento difformi dalle condizioni contrattuali concordate con LIAL. Il Procacciatore sarà, "
        "pertanto, responsabile per i danni cagionati, ove LIAL fosse chiamata a rispondere sulla base "
        "dell'affidamento ingenerato nei clienti in relazione a deroghe non autorizzate alle condizioni "
        "contrattuali.",
    ),
    clause(
        "3.5.",
        "Nell'esecuzione della propria attività il Procacciatore profonderà il massimo sforzo per "
        "promuovere ed incrementare la clientela nonché le vendite dei Prodotti, sottoponendo "
        "immediatamente a LIAL qualsiasi richiesta od ordine ottenuto, con i dettagli necessari e "
        "sufficienti a consentire a LIAL la loro proficua valutazione ed una loro tempestiva evasione.",
    ),
    clause("3.6.", "In particolare, il Procacciatore:"),
    bullets(
        "selezionerà accuratamente i potenziali clienti tra quelli in linea con le caratteristiche predefinite da LIAL;",
        "si asterrà dal trattare con soggetti di dubbia solvibilità o affidabilità;",
        "illustrerà al cliente le caratteristiche dei Prodotti offerti dalla LIAL in modo chiaro e "
        "corretto, astenendosi dall'attribuire caratteristiche non veritiere;",
        "promuoverà la vendita dei Prodotti esclusivamente mediante l'uso dell'applicazione fornita da "
        "LIAL e/o dei modelli di proposta contrattuale dalla medesima predisposti e solo al prezzo "
        "fissato e aggiornato nel listino prezzi;",
        "informerà il cliente che il perfezionamento di qualsiasi contratto è subordinato "
        "all'accettazione da parte di LIAL.",
    ),
    clause(
        "3.7.",
        "La proposta contrattuale del cliente, insieme alla dichiarazione di consenso al trattamento dei "
        "dati personali, deve essere trasmessa tempestivamente a LIAL, la quale si riserva la facoltà di "
        "accettarla, o meno, a proprio insindacabile giudizio. In caso di non accettazione della proposta "
        "contrattuale, il Procacciatore riconosce che nulla gli sarà dovuto, a qualsivoglia titolo.",
    ),
    clause(
        "3.8.",
        "Il Procacciatore dovrà acquisire tutti i dati del cliente necessari in relazione alla tipologia "
        "del rapporto da instaurare; in particolare, dovrà verificare i dati anagrafici del cliente "
        "mediante verifica di un valido documento di identità in originale. Ove il cliente sia una "
        "società, il Procacciatore dovrà verificare i poteri di rappresentanza di colui o coloro i quali "
        "agiscano in nome e per conto della medesima.",
    ),
    clause(
        "3.9.",
        "Il Procacciatore deve comunicare a LIAL tutte le informazioni acquisite, ovvero acquisibili con "
        "l'utilizzo della normale diligenza, che potrebbero influire sulla decisione della medesima di "
        "concludere o recedere da un contratto. In caso di inadempimento, il Procacciatore potrà essere "
        "ritenuto responsabile di tutti i danni patiti da LIAL, con obbligo del loro integrale risarcimento.",
    ),
    clause(
        "3.10.",
        "L'accettazione della proposta contrattuale da parte di LIAL avverrà secondo le modalità previste "
        "da ogni singolo contratto e la medesima comunicherà al cliente l'avvenuto perfezionamento del "
        "Contratto, trasmettendogli la relativa documentazione.",
    ),
    clause(
        "3.11.",
        "Il Procacciatore si impegna a dare a LIAL immediata notizia di qualsiasi reclamo o contestazione "
        "che venisse fatta dal cliente in corso di esecuzione del contratto e non potrà assumere alcun "
        "impegno verbale o scritto per conto di LIAL.",
    ),
    clause(
        "3.12.",
        "Con cadenza regolare, nei termini concordati con LIAL, il Procacciatore dovrà relazionare in "
        "ordine allo svolgimento della propria attività, eventualmente anche mediante la partecipazione a "
        "incontri di coordinamento con altri collaboratori ovvero personale dipendente di LIAL.",
    ),

    heading("4. Durata del contratto"),
    clause(
        "4.1.",
        "Il presente Contratto entra in vigore alla data della sua sottoscrizione e sarà valido fino "
        "all'avvenuta disdetta di una delle Parti, da inviarsi per iscritto a mezzo di raccomandata a.r. "
        "ovvero tramite posta elettronica certificata con un preavviso di 30 (trenta) giorni rispetto al "
        "termine indicato.",
    ),
    clause(
        "4.2.",
        "Il Contratto si risolverà definitivamente all'ultimo giorno del periodo di preavviso ed il "
        "Procacciatore, fin da ora, si impegna a cessare l'attività di promozione degli affari senza "
        "specifico diverso accordo con LIAL.",
    ),
    clause("4.3.", "Restano in ogni caso salve le ipotesi di risoluzione di cui all'articolo 9."),

    heading("5. Procura all'incasso"),
    clause("5.1.", "Il Procacciatore non è autorizzato a ricevere pagamenti per conto di LIAL."),
    clause(
        "5.2.",
        "In nessun caso il Procacciatore potrà trattenere quanto riscosso dal Cliente, ovvero detrarre da "
        "tali somme alcunché, neppure imputandolo a titolo di rimborso o compensazione di propri crediti "
        "verso LIAL.",
    ),

    heading("6. Attività e materiale promozionale"),
    clause(
        "6.1.",
        "Nel corso dello svolgimento del rapporto, LIAL consegnerà al Procacciatore, anche digitalmente, "
        "tutta la documentazione illustrativa e promozionale (dépliant, listini prezzi, ecc.) dei Prodotti "
        "offerti, nonché la documentazione contrattuale ed amministrativa (proposte contrattuali, "
        "modulistica RID, ecc.).",
    ),
    clause(
        "6.2.",
        "Tutta la documentazione dovrà essere utilizzata secondo le modalità indicate da LIAL. Tale "
        "documentazione assume carattere riservato, costituisce il know-how di LIAL e resta di proprietà "
        "di LIAL.",
    ),
    clause(
        "6.3.",
        "Il Procacciatore ha l'obbligo di custodire con la dovuta diligenza detto materiale, rispondendo "
        "nei confronti di LIAL in caso di deterioramento, perdita, furto e/o danneggiamento.",
    ),
    clause(
        "6.4.",
        "Allo scopo di consentire al Procacciatore di raggiungere una adeguata conoscenza delle "
        "caratteristiche tecniche e commerciali dei Prodotti, LIAL potrà organizzare, nei tempi e con le "
        "modalità che saranno di volta in volta comunicati, momenti formativi e di aggiornamento legati "
        "alla qualificazione professionale. Gli incontri potranno essere a pagamento e la partecipazione "
        "ai medesimi potrà essere richiesta da LIAL per il mantenimento di un'adeguata professionalità del "
        "Procacciatore.",
    ),

    heading("7. Compenso e scatti di carriera"),
    clause(
        "7.1.",
        "Il Procacciatore maturerà il diritto di ricevere un compenso sulle vendite dei Prodotti da lui "
        "concluse e andate a buon fine. Il compenso costituisce la remunerazione globale e onnicomprensiva "
        "di tutte le attività svolte e le spese sostenute dal Procacciatore per l'esecuzione della propria "
        "attività (a titolo di mero esempio, rapporti con i collaboratori, attività di promozione delle "
        "vendite, trasferte, assistenza per gli incassi, iniziative promozionali, ecc.).",
    ),
    clause(
        "7.2.",
        "Il compenso deve intendersi riconosciuto al Procacciatore anche a copertura del rischio di "
        "impresa e, pertanto, egli non potrà rivendicare alcunché a titolo di risarcimento danno, perdite "
        "o indennizzo di sorta.",
    ),
    clause("7.3.", "LIAL riconoscerà al Procacciatore i compensi analiticamente indicati nell'Allegato A del presente Contratto."),
    clause(
        "7.4.",
        "Il diritto al compenso maturerà solamente una volta attivata la fornitura del Prodotto. Le Parti "
        "espressamente riconoscono che il Procacciatore non avrà diritto a compenso alcuno in caso di:",
    ),
    bullets(
        "mancata accettazione del contratto da parte di LIAL, a proprio insindacabile giudizio;",
        "mancata esecuzione del contratto per causa non imputabile a LIAL;",
        "mancato pagamento totale da parte del cliente, ove il Procacciatore abbia violato l'obbligo di "
        "diligenza e non abbia verificato la solvibilità del medesimo.",
    ),
    clause(
        "7.5.",
        "Nell'ipotesi in cui il compenso fosse già stato riconosciuto al Procacciatore, LIAL provvederà a "
        "detrarne il valore dai successivi compensi maturati.",
    ),
    clause(
        "7.6.",
        "Nulla sarà dovuto a titolo di compenso per gli affari conclusi direttamente da LIAL con terzi che "
        "il Procacciatore aveva in precedenza acquisito come clienti per affari dello stesso tipo.",
    ),
    clause(
        "7.7.",
        "Con il proficuo svolgimento della propria attività, inoltre, il Procacciatore avrà diritto agli "
        "avanzamenti di carriera previsti da LIAL e analiticamente indicati nello schema che si allega al "
        "presente contratto sotto la lettera «B».",
    ),

    heading("8. Liquidazione e pagamento"),
    clause(
        "8.1.",
        "Nei 45 (quarantacinque) giorni successivi allo scadere del mese in cui sono maturati i compensi "
        "(mese di attivazione dei contratti), LIAL invierà al Procacciatore una comunicazione nella quale "
        "sono indicati gli importi in liquidazione e l'invito ad emettere fattura a carico di LIAL, a "
        "titolo di compenso.",
    ),
    clause(
        "8.2.",
        "Ai fini della determinazione del corrispettivo, il Procacciatore riconosce la validità delle "
        "verifiche e dei conteggi effettuati da LIAL. Eventuali contestazioni dovranno essere sollevate "
        "entro il termine perentorio di 5 (cinque) giorni dalla comunicazione degli importi; trascorso "
        "invano tale termine, gli importi comunicati da LIAL si intenderanno definitivamente approvati e "
        "il Procacciatore decadrà dal proprio diritto di sollevare eccezioni e contestazioni.",
    ),
    clause(
        "8.3.",
        "Anche in caso di contestazioni sulla misura dei compensi, LIAL corrisponderà al Procacciatore i "
        "compensi calcolati e fatturati sulle somme non contestate, entro il termine di 5 (cinque) giorni "
        "dall'emissione della fattura, mentre le eventuali ulteriori somme saranno versate da LIAL alla "
        "definizione della controversia, previa emissione di idonea fattura da parte del Procacciatore.",
    ),
    clause(
        "8.4.",
        "Il Procacciatore prende atto che, in ragione del dovere di riservatezza che incombe su LIAL, non "
        "potrà essergli trasmessa copia delle fatture emesse ai clienti, né alcun dato specifico "
        "riguardante i consumi dei singoli clienti, bensì esclusivamente dati aggregati in via cumulativa "
        "e non analitica.",
    ),
    clause(
        "8.5.",
        "LIAL potrà sospendere qualsivoglia pagamento, anche se riferito a compensi già maturati e/o "
        "liquidati, qualora risulti la non corretta attivazione dei contratti procurati da parte del "
        "Procacciatore; ciò potrebbe risultare nei seguenti casi, da considerarsi, comunque, "
        "esemplificativi e non esaustivi:",
    ),
    bullets(
        "traffico anomalo, per entità o per qualità, rispetto al profilo del cliente risultante dalla sua "
        "proposta contrattuale;",
        "dimensioni e caratteristiche del cliente non compatibili con la sua proposta contrattuale;",
        "irreperibilità del cliente;",
        "mancata o inesatta identificazione del cliente e mancanza dei documenti necessari per "
        "l'attivazione della fornitura.",
    ),

    heading("9. Risoluzione del rapporto e conseguenze"),
    clause(
        "9.1.",
        "LIAL, fermo restando il diritto al risarcimento dei danni subiti, avrà diritto a risolvere il "
        "presente rapporto ai sensi e per gli effetti di cui all'art. 1456 c.c., senza la corresponsione "
        "di qualsivoglia indennità o risarcimento, in caso di violazione da parte del Procacciatore, "
        "ovvero suoi collaboratori e/o dipendenti, anche a una sola delle obbligazioni di cui ai seguenti "
        "articoli: art. 2.5., 2.6. e 2.7.; art. 3.3., 3.4., 3.8. e 3.9.; art. 5.; art. 6.2.; art. 10; "
        "art. 12; art. 14.4. e 14.6.",
    ),
    clause("9.2.", "Il rapporto potrà, inoltre, essere risolto nei seguenti casi:"),
    bullets(
        "ove il Procacciatore abbia riportato condanne civili o penali che possano pregiudicarne il buon "
        "nome od ostacolare lo svolgimento regolare dell'attività;",
        "in caso di inosservanza delle norme in materia di sicurezza sui luoghi di lavoro;",
        "ove il Procacciatore non abbia corrisposto, anche per una sola mensilità, i compensi e le "
        "retribuzioni in favore dei propri collaboratori o personale dipendente;",
        "inaffidabilità o insolvenza, anche transitorie, del Procacciatore (o del suo rappresentante, in "
        "caso di società) evidenziate, a mero titolo di esempio, da protesti o pignoramenti, specie nei "
        "confronti dell'erario e di enti previdenziali ed assistenziali;",
        "sopravvenuta incapacità del Procacciatore, se persona fisica, ovvero liquidazione o "
        "sottoposizione a procedure concorsuali se persona giuridica.",
    ),
    clause(
        "9.3.",
        "Nelle ipotesi di recesso per giusta causa sopra elencate, il Contratto si intenderà risolto di "
        "diritto, senza corresponsione di qualsivoglia indennità, e il Procacciatore avrà diritto "
        "unicamente ai compensi maturati alla data del recesso, restando espressamente escluso il "
        "pagamento di ulteriori importi, maturati e maturandi, dopo detta data e salvo restando il diritto "
        "di LIAL di pretendere il risarcimento dei danni eventualmente subiti.",
    ),
    clause(
        "9.4.",
        "In ogni altro caso di risoluzione del presente Contratto, LIAL corrisponderà al Procacciatore i "
        "compensi che matureranno a suo favore nei mesi successivi all'evento interruttivo del rapporto, "
        "inerenti a contratti stipulati anteriormente alla data di cessazione del Contratto. Le Parti "
        "espressamente e concordemente convengono che tali compensi saranno oggetto di compensazioni con "
        "eventuali crediti di LIAL nei confronti del Procacciatore, comunque maturati.",
    ),
    clause(
        "9.5.",
        "Il Procacciatore si asterrà dal contattare ulteriormente i clienti ai fini di proporre loro "
        "ulteriori e diverse forniture per un periodo di almeno 36 (trentasei) mesi dalla risoluzione del "
        "presente Contratto.",
    ),
    clause(
        "9.6.",
        "In caso contrario, LIAL avrà diritto di pretendere dal Procacciatore una penale pari a euro 10 "
        "(dieci) al mese per ogni cliente e per ogni mese di mancata fornitura fino al trentaseiesimo mese "
        "indicato al precedente punto 9.5.",
    ),
    clause(
        "9.7.",
        "Dalla data di cessazione del rapporto, per qualsiasi motivo, i contratti e gli affari procacciati "
        "resteranno definitivamente e gratuitamente acquisiti da LIAL, così come ogni informazione e dato "
        "a essi inerente.",
    ),
    clause(
        "9.8.",
        "Entro 7 (sette) giorni dal verificarsi di una qualsiasi delle cause di scioglimento del presente "
        "rapporto, il Procacciatore dovrà immediatamente interrompere l'utilizzo del materiale "
        "promozionale, illustrativo e contrattuale fornitogli da LIAL, provvedendo alla relativa "
        "restituzione, e, in ogni caso, dovrà cessare qualsiasi forma di utilizzo di segni distintivi e/o "
        "marchi riferibili a LIAL.",
    ),
    clause(
        "9.9.",
        "In caso di inottemperanza all'obbligo di restituzione di cui al comma precedente, LIAL è "
        "espressamente autorizzata a sospendere il pagamento dell'eventuale compenso spettante al "
        "Procacciatore, fino all'integrale restituzione o al recupero del loro valore.",
    ),

    heading("10. Intuitus personae e cessione del contratto"),
    clause(
        "10.1.",
        "LIAL dichiara di essersi determinata a stipulare il presente Contratto sulla base di un rapporto "
        "di fiducia verso il Procacciatore: pertanto, ove il medesimo sia una società, ogni mutamento "
        "dell'assetto proprietario o del suo organo amministrativo dovrà preventivamente essere comunicato "
        "per iscritto a LIAL, la quale potrà, entro i successivi 30 (trenta) giorni, risolvere di diritto e "
        "con effetto immediato il presente Contratto, ai sensi e per gli effetti di cui all'articolo 1456 c.c.",
    ),
    clause(
        "10.2.",
        "Anche la mancata preventiva comunicazione del mutamento di proprietà o amministrazione costituirà "
        "motivo di risoluzione immediata del Contratto, ai sensi dell'art. 1456 c.c.",
    ),
    clause(
        "10.3.",
        "Il Procacciatore non potrà trasferire a terzi il Contratto, neanche indirettamente attraverso "
        "cessione di azienda o di ramo d'azienda, né potrà cedere a terzi i crediti che dovesse vantare nei "
        "confronti di LIAL in virtù del presente Contratto.",
    ),

    heading("11. Clausola di esonero di responsabilità"),
    clause(
        "11.1.",
        "Anche in conseguenza del precedente art. 3.3., LIAL non sarà responsabile di qualsiasi rapporto "
        "intercorso fra il Procacciatore e i potenziali clienti.",
    ),
    clause("11.2.", "In ogni caso, LIAL non potrà essere ritenuta responsabile di eventuali ritardi nella erogazione dei servizi al cliente."),

    heading("12. Marchi e segni distintivi"),
    clause(
        "12.1.",
        "Il Procacciatore è tenuto ad usare marchi e/o segni distintivi di LIAL e/o dei fornitori dei "
        "servizi al solo fine di identificare e pubblicizzare i Prodotti nel contesto della sua attività di "
        "Procacciatore.",
    ),
    clause(
        "12.2.",
        "Il diritto del Procacciatore di usare marchi e/o segni distintivi di LIAL e/o dei fornitori dei "
        "servizi come previsto al comma precedente cessa immediatamente con la cessazione, per qualsiasi "
        "causa, del presente contratto.",
    ),
    clause(
        "12.3.",
        "Il Procacciatore non potrà effettuare campagne pubblicitarie e/o promozionali relative alle "
        "attività di cui al presente Contratto, senza la preventiva ed espressa autorizzazione di LIAL.",
    ),
    clause(
        "12.4.",
        "Il Procacciatore non potrà intraprendere alcuna azione che possa arrecare pregiudizio ai citati "
        "marchi e/o segni distintivi, né utilizzerà o registrerà denominazioni o marchi simili o "
        "confondibili con gli stessi.",
    ),
    clause("12.5.", "Tutti gli impegni di cui ai commi precedenti rimarranno validi ed efficaci anche dopo la cessazione del presente Contratto, per qualsiasi causa."),
    clause(
        "12.6.",
        "Fermo ed impregiudicato quanto espressamente previsto nella presente autorizzazione, il "
        "Procacciatore si impegna, in caso di scioglimento del rapporto contrattuale per qualsiasi motivo, "
        "a cessare ogni utilizzo dei marchi e/o segni distintivi di LIAL e/o dei fornitori di servizi. "
        "Inoltre, il Procacciatore eviterà qualsiasi comportamento idoneo ad ingenerare il convincimento "
        "che egli continui ad essere un Procacciatore di LIAL.",
    ),
    clause(
        "12.7.",
        "Durante il rapporto contrattuale ed anche dopo la sua conclusione, per qualsiasi causa, il "
        "Procacciatore dovrà osservare la massima segretezza sulle conoscenze acquisite durante il periodo "
        "contrattuale, relative a pratiche commerciali e/o tecniche in atto presso LIAL e/o i fornitori di "
        "servizi.",
    ),

    heading("13. Forma del contratto, comunicazioni alle Parti e modifiche contrattuali"),
    clause(
        "13.1.",
        "Qualsiasi comunicazione fra le Parti dovrà essere effettuata mediante lettera raccomandata con "
        "avviso di ricevimento o mediante l'utilizzo dell'indirizzo P.E.C. indicato in epigrafe, ovvero "
        "successivamente comunicato.",
    ),
    clause(
        "13.2.",
        "Qualsiasi modifica relativa al presente Contratto, comprese eventuali variazioni degli importi dei "
        "compensi e delle condizioni o modalità di pagamento, ai fini della sua validità ed efficacia, dovrà "
        "risultare da atto scritto recante la sottoscrizione di entrambe le Parti.",
    ),
    clause(
        "13.3.",
        "La mancata contestazione da parte di LIAL, anche se ripetuta, di un inadempimento del Procacciatore "
        "non comporterà modifica o cessazione di efficacia della norma violata, né la decadenza di LIAL dal "
        "diritto di contestare detto inadempimento in un momento futuro.",
    ),

    heading("14. Trattamento dei dati personali"),
    clause(
        "14.1.",
        "Le Parti si conformano, agli effetti del presente Contratto, alle disposizioni del Regolamento in "
        "materia di protezione dei dati personali di cui al Regolamento generale sulla protezione dei dati "
        "(Reg. UE n. 2016/679) e successive modifiche ed integrazioni.",
    ),
    clause(
        "14.2.",
        "Il Procacciatore, preso atto dell'informativa resa ai sensi dell'art. 13 del Reg. UE n. 2016/679, "
        "autorizza LIAL a trattare i propri dati comuni e quelli sensibili, ai fini dell'esecuzione del "
        "presente Contratto. I dati saranno trattati sia manualmente, che elettronicamente e potranno essere "
        "comunicati a terzi in esecuzione di obblighi legali ovvero per la elaborazione richiesta per "
        "adempiere finalità amministrativo-contabili. La revoca dell'autorizzazione al trattamento dei dati "
        "personali potrà comportare l'impossibilità della prosecuzione del presente Contratto. I diritti del "
        "Procacciatore in relazione al trattamento dei propri dati personali sono quelli di cui al Reg. UE n. "
        "2016/679.",
    ),
    clause(
        "14.3.",
        "Il Procacciatore autorizza espressamente LIAL a comunicare i propri dati personali ai fornitori di "
        "servizi nella misura e con i limiti necessari a consentire il corretto e puntuale adempimento delle "
        "obbligazioni ricadenti su LIAL nell'ambito dei rapporti con i medesimi.",
    ),
    clause(
        "14.4.",
        "Il Procacciatore assumerà la veste di Responsabile/Sub-Responsabile del trattamento dei dati "
        "personali, impegnandosi ad accettare e rispettare le condizioni/istruzioni contenute nella "
        "comunicazione dal medesimo sottoscritta all'atto della stipula del presente Contratto. Tale "
        "comunicazione, una volta sottoscritta, dovrà essere restituita a LIAL.",
    ),
    clause(
        "14.5.",
        "Nel caso in cui il Procacciatore si avvalga dell'opera di collaboratori, egli si impegna a "
        "designarli quali Incaricati del trattamento dei dati personali, se persone fisiche, ovvero a far "
        "loro accettare la nomina a Responsabile/Sub-Responsabile del trattamento, se enti collettivi.",
    ),
    clause(
        "14.6.",
        "Il Procacciatore si impegna ad informare i clienti che i dati personali dagli stessi forniti saranno "
        "trasmessi a LIAL e ai fornitori dei Prodotti per le finalità del presente Contratto. LIAL, insieme "
        "ai contratti di fornitura, si impegna a far sottoscrivere ai clienti idonee autorizzazioni al "
        "trattamento dei dati personali. Il mancato rispetto, da parte del Procacciatore, degli obblighi che "
        "gli competono in qualità di Responsabile/Sub-Responsabile per conto di LIAL del trattamento dei dati "
        "personali di cui sopra comporterà la risoluzione di diritto del presente contratto, nonché l'obbligo "
        "per il Procacciatore di tenere indenne LIAL, qualora da tale inosservanza sorga in capo alla stessa "
        "l'obbligo al risarcimento dei danni cagionati a terzi.",
    ),

    heading("15. Clausole nulle o inefficaci"),
    clause(
        "15.1.",
        "Qualora una o più clausole del presente Contratto fossero o divenissero contrarie a norme imperative "
        "o di ordine pubblico, esse saranno considerate come non apposte e non incideranno sulla validità del "
        "contratto, fatta salva l'ipotesi che l'eliminazione della clausola nulla comprometta la validità del "
        "presente contratto.",
    ),
    clause("15.2.", "Ove ciò dovesse accadere, le Parti si impegnano a concordare in buona fede la sostituzione della clausola nulla con altra valida."),

    heading("16. Foro competente"),
    clause(
        "16.1.",
        "Per qualsiasi controversia che potesse insorgere tra le Parti circa l'interpretazione o esecuzione "
        "del presente Contratto, le Parti convengono la competenza esclusiva del Foro di Torino.",
    ),

    heading("Allegati"),
    paragraph("Sono allegati al presente Contratto e ne costituiscono parte integrante e sostanziale, i seguenti documenti:"),
    bullets(
        "Allegato A) — Tabella dei compensi",
        "Allegato B) — Schema degli avanzamenti di carriera",
    ),
    signature(
        "Il Procacciatore dichiara di aver letto e di accettare integralmente il presente Contratto, che "
        "viene sottoscritto mediante il codice di conferma ricevuto via email."
    ),
]


# =============================================================================
# 2. L'allegato al contratto
# =============================================================================
#
# Italian law (artt. 1341 e ss. c.c.) requires the clausole vessatorie to be
# approved separately from the contract itself, which is why this is its own
# document with its own acceptance rather than being folded into the one
# above. It also carries the list of the contract's own annexes.
#
# Allegato A (tabella dei compensi) and Allegato B (schema degli avanzamenti
# di carriera) are named here but their figures are NOT reproduced: the text
# supplied for them was a duplicate of the contract and contained no tables.
# They are numbers people agree to, so they are left to be filled in rather
# than invented -- see the `table()` helper at the top of this file, built
# for exactly that.

_ATTACHMENT_BLOCKS: list[dict] = [
    heading("Approvazione specifica delle clausole (artt. 1341 e ss. c.c.)"),
    paragraph(
        "Ai sensi e per gli effetti degli artt. 1341 e ss. del codice civile, il Procacciatore dichiara di "
        "aver attentamente esaminato il contenuto delle clausole del Contratto e di approvare "
        "specificamente le seguenti clausole:"
    ),
    bullets(
        "n. 2 — Oggetto del contratto",
        "n. 3 — Modalità di svolgimento del rapporto",
        "n. 5 — Procura all'incasso",
        "n. 6 — Attività e materiale promozionale",
        "n. 7 — Compenso e scatti di carriera",
        "n. 8 — Liquidazione e pagamento",
        "n. 9 — Risoluzione del rapporto e conseguenze",
        "n. 10 — Intuitus personae e cessione del contratto",
        "n. 11 — Clausola di esonero di responsabilità",
        "n. 12 — Marchi e segni distintivi",
        "n. 16 — Foro competente",
    ),

    heading("Allegato A — Tabella dei compensi"),
    paragraph(
        "LIAL riconosce al Procacciatore i compensi indicati in questa tabella, alle condizioni previste "
        "dagli articoli 7 e 8 del Contratto. Il diritto al compenso matura solamente una volta attivata "
        "la fornitura del Prodotto."
    ),
    # DA COMPLETARE -- sostituire con table(columns=[...], rows=[[...]]) non
    # appena i compensi reali sono disponibili, e incrementare la version.
    paragraph(
        "La tabella dei compensi in vigore viene comunicata da LIAL e forma parte integrante e "
        "sostanziale del Contratto."
    ),

    heading("Allegato B — Schema degli avanzamenti di carriera"),
    paragraph(
        "Con il proficuo svolgimento della propria attività il Procacciatore ha diritto agli avanzamenti "
        "di carriera previsti da LIAL, secondo lo schema che forma parte integrante e sostanziale del "
        "Contratto ai sensi dell'articolo 7.7."
    ),
    # DA COMPLETARE -- come sopra.

    signature(
        "Il Procacciatore dichiara di aver letto il presente Allegato e di approvarne integralmente il "
        "contenuto, ivi comprese le clausole specificamente elencate."
    ),
]


COLLABORATION_DOCUMENTS: tuple[CollaborationDocument, ...] = (
    CollaborationDocument(
        key="CONTRACT",
        version="2026.1",
        title="Contratto di procacciamento di affari",
        subtitle="Lial Energy S.r.l. — Torino, corso Matteotti 30",
        acceptance_label="Ho letto e accetto integralmente il contratto di procacciamento di affari.",
        blocks=_CONTRACT_BLOCKS,
    ),
    CollaborationDocument(
        key="SPECIFIC_CLAUSES",
        version="2026.2",
        title="Allegato al contratto",
        subtitle="Approvazione specifica delle clausole · Allegato A e Allegato B",
        acceptance_label="Ho letto e accetto l'allegato al contratto, comprese le clausole specificamente elencate.",
        blocks=_ATTACHMENT_BLOCKS,
    ),
    # Allegato A (tabella dei compensi) e Allegato B (schema degli
    # avanzamenti di carriera) sono già dichiarati nell'allegato qui sopra,
    # ma senza le rispettive TABELLE: il testo fornito per l'allegato era un
    # duplicato del contratto e non conteneva alcuna tabella. Sostituire i
    # due paragrafi segnati "DA COMPLETARE" in _ATTACHMENT_BLOCKS con
    # table(columns=[...], rows=[[...]]) e incrementare la version di questo
    # documento: nient'altro cambia, la dashboard rende la tabella da sé.
)


def document_by_key(key: str) -> CollaborationDocument | None:
    return next((doc for doc in COLLABORATION_DOCUMENTS if doc.key == key), None)


def required_versions() -> dict[str, str]:
    """{key: current version} -- what an application must accept, right now."""
    return {doc.key: doc.version for doc in COLLABORATION_DOCUMENTS}
