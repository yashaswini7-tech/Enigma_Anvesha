# Decisions and trade-offs

- **14 ground-truth items from a 15-entry mix.** The spec's mix lists 15 kinds of items but fixes the total at 14. The "old fixed deposit" and the "second bank account visible only through AIS interest" are modelled as one item: an old FD at a second bank (Bank of Baroda), seen only as AIS deposit interest.
- **The cancelled SIP is scored separately.** The ICICI Prudential SIP stopped in Aug 2024 and its units were redeemed (AIS shows a sale). It sits in `closed_items` in the ground truth. The right behaviour is to surface it as "possibly closed — confirm". It counts neither as a true positive nor as a false positive for the 14.
- **Ground truth links to evidence rows.** Each ground-truth item lists the statement refs and AIS rows that belong to it. Scoring matches predictions to truth by overlapping evidence, not by fuzzy name matching. The score therefore checks that the tool found the right thing for the right reason.
- **Default local model is `llama3.2:3b`.** It was already installed in Ollama on the build machine. `qwen2.5:3b` works too through `ANVESHA_OLLAMA_MODEL`.
- **PDF statements are parsed line by line with a regex** over pdfplumber text rather than with table extraction. This is robust for our generated layout. Real bank PDFs vary, which is noted under Limitations.
- **Synthetic AIS uses descriptive categories** ("Interest from deposit", "Dividend") rather than official information codes. We did not want to invent codes we had not verified.
