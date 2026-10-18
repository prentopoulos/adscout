# AI-written text around computed figures

Use this when a model writes prose that states or refers to numbers: reports, briefs,
summaries. The pattern comes from the Compute Cost & Risk Monitor market brief. Every hole
listed here was found by a code review, so build against them from the start.

## The pattern

1. **Code computes every figure** into a fact set. Each fact has an ID, a value, its displayed
   text, a unit, a meaning and links to its source records.
2. **The model writes words only.** It refers to figures through placeholders such as
   `[[fact_id]]`, never digits, and code fills the placeholders in.
3. **A deterministic validator rejects a draft section** that has:
   - a digit outside placeholders and outside the known names;
   - a number word, including plurals, multiples and ordinals: "thousands", "halved",
     "tenfold", "both", "neither", "first". Keep the project's defined terms allowed (for
     example "absent once");
   - an unknown placeholder, or a missing required one;
   - a banned claim word, such as "forecast", "index" or "cheapest";
   - a line break or "#", because a heading in prose could end the checked region early.
4. **An independent check re-derives every number and time** in the filled text from the
   stored data. It is a module that imports none of the code it checks.
5. **Retry, then fall back.** A filled draft that fails the check counts as rejected inside the
   retry loop, so it gets the retry. After the last attempt, use a plain template written by
   code.

## Keep the validator and the check in step

- **Names:** they must agree on what counts as a name. Model and product names hold digits:
  "H100", "US West 3", and the bare model name as well as the full one.
- **Number formats:** they must agree on formats, such as thousands separators: "1,000", not
  "1000".
- **Tests:** test both directions. A draft the validator accepts must pass the check, and a
  tampered figure must fail it.

## Data and cost safety

- **Data gate:** when the model may see only public or synthetic data, decide by every input
  the text draws on (for example every snapshot behind "changes since"), not just the latest.
  Refuse mixed data before any request.
- **Efficiency:** derive the check's values once, and release the database before any API call.
- **Testing and runs:** tests use a fake sender. Real runs are started by hand, under the spend
  gate.
- **Run records:** every run keeps one. It holds the model, the prompt version and its SHA-256,
  request IDs, usage and cost, plus each attempt's reply and rejection reasons. Keep failed runs
  too.

## Wording

- **State scope exactly:** "for this GPU and count", not "for this size", when the figure covers
  more than the named item.
- **Counts in the text must cover the same rows** as the table beside them.
- **Name the feature plainly** ("AI-powered market brief"). Don't add reassurance taglines.
