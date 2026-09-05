# Piano: Cashback da riscatto fatture fornitori-partner

## Lavoro collegato già completato (2026-09-05, stessa sessione)

- [x] **Bonifico wallet disabilitato di default per tutti** (clienti e
      promoter), abilitabile individualmente solo per promoter specifici.
      Migrazione `0019_wallet_transfer_gate.py` (colonna `wallets.can_transfer`,
      default `false`). Abilitati oggi: Alessandro Pantano, Marco Web. Toggle
      admin in "Anagrafiche Promoter" (bottone "Bonifico: ON/OFF" per riga),
      verificato live: un utente non abilitato riceve `TransferNotAllowedError`
      / 403, i due abilitati passano. Non è parte del progetto cashback in
      sé, ma stessa sessione/stesso file di dominio wallet.

**Stato: solo progettazione. Zero righe di codice scritte per questo progetto.**
Se stai riprendendo questo lavoro dopo un crash/reset di sessione, questo file
ti dice esattamente a che punto siamo — leggilo prima di chiedere di nuovo
all'utente cosa vuole, la risposta è già qui sotto.

Relazione completa (design ragionato, diagramma del flusso, tabelle):
artifact pubblicato il 2026-09-05, titolo "Cashback Circolare"
(`claude.ai/code/artifact/c79ffd6e-b10b-421b-b3dc-b71dfdba398f` — se il link
non è più raggiungibile, il riassunto completo è comunque qui sotto, non si
perde nulla).

## L'idea in una frase

Il cliente riscatta come credito interno il valore di una bolletta già pagata
a un fornitore-partner esterno (Lial fa da broker), pagando a Lial solo il 3%
di quell'importo via bonifico; alla conferma admin riceve credito = 100% +
3% bonus, spendibile come sconto sui prodotti esterni dello shop (mai sui
prodotti interni Lial, mai in contanti).

**Principio cardine, non negoziabile**: il credito nasce SOLO da un ingresso
reale di denaro (il bonifico del 3%). Non deve mai nascere dallo spendere un
credito già esistente — altrimenti si autogenera valore dal nulla.

## Cosa esiste già nel codice (riusabile, non da ricostruire)

- [x] Wallet interno (`apps/api/app/domains/wallets/`) — indirizzo, saldo,
      storico append-only, tipo `ADMIN_CREDIT` già pensato per un accredito
      legato a un acquisto (`reference_contract_id`).
- [x] Sistema di upload documenti privati (usato oggi per documenti sensibili
      sui contratti) — riusabile per la foto della fattura.
- [x] Pattern di stato-macchina con conferma admin, già usato per i contratti
      (`contracts/state_machine.py`) — stesso pattern da replicare per il
      riscatto fattura.
- [x] Bottone "Ricarica" già aggiunto alla tabella wallet admin globale
      (`admin-wallets-panel.tsx`) — lavoro completato in questa sessione, non
      c'entra con il progetto cashback ma è nello stesso file/area.

## Cosa NON esiste ancora (da costruire)

- [ ] Anagrafica `partners` (fornitori esterni tipo Eviso)
- [ ] Tabella/dominio `invoice_redemptions` (la richiesta di riscatto, con
      stato: Caricata → Verificata → Attesa pagamento 3% → Confermata →
      Accreditata, più `Rifiutata`)
- [ ] Campo `category` sul prodotto (`INTERNAL` / `DROPSHIPPING` / `PARTNER`)
- [ ] Campo `credit_discount_percentage` sul prodotto (solo per le ultime due
      categorie)
- [ ] Campo `source` su `wallet_transactions` (per distinguere un riscatto
      fattura da una correzione manuale admin, senza dover leggere la nota)
- [ ] Campo `reference_invoice_redemption_id` su `wallet_transactions`
- [ ] Percorso guidato cliente (wizard: foto → seleziona partner → OCR
      propone importo → invio → stato "in verifica")
- [ ] Integrazione OCR per la lettura assistita dell'importo (assistente,
      MAI conferma automatica — la verifica resta sempre umana)
- [ ] UI admin per verificare le fatture caricate e confermare l'importo
- [ ] UI admin per confermare la ricezione del bonifico del 3%
- [ ] Logica che scrive le due righe di transazione (base + bonus) alla
      conferma
- [ ] Sconto in crediti selezionabile nel checkout, con residuo pagato in
      bonifico come oggi

## Decisioni prese

- [x] **I prodotti interni Lial NON generano mai cashback automatico.**
      L'unica fonte di credito è il riscatto fattura partner. Confermato
      esplicitamente dall'utente il 2026-09-05.

## Decisioni ancora da prendere (blocca l'inizio della Fase corrispondente)

- [ ] **Fatture duplicate/false**: oltre alla verifica umana, serve un
      controllo automatico numero-fattura + fornitore per bloccare doppi
      riscatti involontari?
- [ ] **Pagamento del residuo**: sempre bonifico come oggi, o si prevede in
      futuro un altro metodo? (Oggi non esiste alcun `PaymentProvider` reale
      nel sistema — sarebbe uno sviluppo separato.)
- [ ] **Scadenza dei crediti**: restano validi per sempre o decadono dopo un
      periodo?
- [ ] **Tetto alla percentuale configurabile** sui prodotti: libera (anche
      100%) o limitata da un tetto di sistema (es. mai oltre il 50%)?
- [ ] **Anagrafica fornitori-partner**: solo nome/logo, o anche referente,
      accordo di partnership, percentuale che Lial riceve da loro?

## Fasi di implementazione proposte (nessuna iniziata)

- [ ] **Fase 0 — Fondamenta**: anagrafica `partners`, categoria + percentuale
      sui prodotti. Nessun euro si muove.
- [ ] **Fase 1 — Caricamento e verifica fattura**: upload + coda di verifica
      admin che conferma l'importo. Si ferma qui, niente pagamento/credito
      ancora.
- [ ] **Fase 2 — Pagamento 3% e accredito**: step di pagamento + conferma
      admin che scrive le due righe (base + bonus) nel wallet. Da qui il
      credito esiste per la prima volta.
- [ ] **Fase 3 — Percorso guidato cliente + OCR**: wizard completo con
      lettura assistita dell'importo.
- [ ] **Fase 4 — Sconto crediti nel checkout**: selezionabile sui prodotti
      dropshipping/partner, residuo in bonifico.

## Come riprendere se una sessione futura parte da zero

1. Leggi questo file per intero prima di fare qualunque altra cosa.
2. Se l'utente dice "continua il lavoro del cashback/crediti", NON richiedere
   da capo le decisioni già segnate come prese sopra.
3. Per le decisioni ancora aperte, chiedi solo quelle — non ripetere l'intera
   relazione, l'utente l'ha già letta nell'artifact.
4. Nessuna Fase è iniziata: se l'utente chiede di "iniziare", si parte dalla
   Fase 0, e solo dopo aver risposto alle decisioni aperte che la bloccano.
5. Aggiorna le checkbox di questo file mano a mano che qualcosa viene deciso
   o costruito — è l'unico modo per cui questo file resti utile la prossima
   volta.
