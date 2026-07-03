// Short, permanent disclosure of what the AI can't verify — trust value
// from docs/PRODUCT_STRATEGY_BETA.md ("only display information we
// actually know"). Kept in one place so app + email copy stay consistent
// (email footer has its own inline copy in templates/email_digest.html —
// same wording, can't share a component across a Jinja template).
export function AiDisclosure() {
  return (
    <p className="text-xs mt-3 max-w-md mx-auto" style={{ color: "var(--text-muted)" }}>
      We can&apos;t verify whether a listing is still open, the poster&apos;s legitimacy, salary accuracy,
      or hiring urgency — job details come from the source board. Always double-check before applying.
    </p>
  );
}
