# Regenerating the parity fixtures

The backend must agree with the frontend's own engine (`tests/test_parity.py`). These scripts export the
frontend's data and "golden" outputs. Run them from a checkout of
[hashir4825/Nova-Helix](https://github.com/hashir4825/Nova-Helix) (they import its `src/app/core/mock/*`):

```bash
cd Nova-Helix
cp <backend>/scripts/frontend-golden/*.ts scripts/
BACKEND=<path to this repo>
npx tsx scripts/dump-data.ts   $BACKEND/app/data                         # metrics, personas, events, questionnaires, seed assignments
npx tsx scripts/dump-golden.ts $BACKEND/tests/fixtures/nova_golden.json  # scores, insights, baselines, samples at D142 14:00 and 03:00
npx tsx scripts/dump-nova-golden.ts $BACKEND/tests/fixtures/nova_chat_golden.json   # Nova replies
```

Then run `make check`. A failure in `tests/test_parity.py` means the backend no longer matches the frontend's
demo data; fix the Python port (or, if the frontend changed on purpose, port the change).
