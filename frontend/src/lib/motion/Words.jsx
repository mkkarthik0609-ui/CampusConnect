/** Splits text into word spans (`.w`) so GSAP can scrub them one by one. Each word stays selectable text in the DOM. */
export function Words({ text, className, wordClassName = "" }) {
  return text.split(" ").map((word, i, all) => (
    <span key={i} className={className}>
      <span className={`w inline-block ${wordClassName}`}>{word}</span>
      {i < all.length - 1 ? " " : null}
    </span>
  ));
}
