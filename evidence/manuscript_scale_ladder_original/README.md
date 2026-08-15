# Recovered manuscript scale-ladder evidence

These files are byte-preserved copies from:

`Downloads/TrueLoop_Customer_Experience_Test/repositories/headline-results/manuscript_2026/recovered`

They were found after the `TC_SUBMIT.zip` review. They are not part of that ZIP. The registration anchor is:

`PREREG_SCALE_LADDER.md` SHA-256 `f128dae481b8bd0951117fd6179f666c8088dd6d2f6dd68925039d16aa6778d5`.

`ladder.py` is the in-memory runner used for the lower rungs, with `tlref.py` beside it for the retained-reference arm. `ladder_mid.jsonl` contains the recovered raw 1-million and 10-million channel records. The three `ladder8_*_final.json` files contain the final 100-million-channel traces. `ladder8_ckpt.py` is the checkpoint runner associated with those final traces. The large checkpoint arrays were deleted in the recovery campaign and are not present here.

Important: the registered and executed runner uses eight-neighbour circular coupling at 0.30. The current TC supplement describes radius-one coupling at 0.20. No file in this directory resolves that discrepancy. Fresh reproductions must state which protocol they execute.
