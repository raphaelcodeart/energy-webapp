/** An amount in LialCash, with the currency name stacked underneath.
 *
 * "+10,00 LialCash" on one line reads as a sentence, and the eye has to
 * parse the whole thing to find the number. Putting the word on its own
 * line, bold but smaller, turns it into a label under a figure: the number
 * is what you scan, "LialCash" is what tells you it isn't euro — which is
 * the entire reason the word is there (see docs/business-rules.md, "LialCash"
 * labeling: wallet credit must never be mistakable for real money).
 *
 * The colour and font size of the number come from the parent cell, exactly
 * as they did when this was a plain string, so every list keeps its own
 * emphasis (red/green for out/in, orange for balances).
 */

function formatCents(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function LialCashAmount({
  cents,
  sign,
  align = "right",
}: {
  cents: number;
  /** "+" / "-" prefix. Omit for a plain balance, which has no direction. */
  sign?: "+" | "-";
  align?: "right" | "left";
}) {
  return (
    <span className={`inline-flex flex-col leading-tight ${align === "right" ? "items-end" : "items-start"}`}>
      <span className="tabular-nums">
        {sign}
        {formatCents(cents)}
      </span>
      {/* Deliberately inherits the parent's colour at reduced opacity rather
          than picking its own: on a red debit row a neutral-grey label would
          look like it belonged to a different column. */}
      <span className="text-[9px] font-bold uppercase tracking-wider opacity-70">LialCash</span>
    </span>
  );
}
