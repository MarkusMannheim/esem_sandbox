# Canonical outputs

Committed so a talk never depends on live compute, a working network or a
conference wifi connection. Regenerate with:

```bash
esem-sandbox run --out outputs/canonical
esem-sandbox compare --ticks 20 --seed 20260904 --out outputs/canonical
```

`comparison.csv` and `comparison.txt` are one paired run: twenty years, one seed,
both legs on the same weather sequence. Read the two cost lines together. The
scheme moves the bill by $10.37bn and the resource cost by $0.51bn, and the
$9.86bn between them is a transfer from generators to consumers rather than a
saving by anybody. The bill alone would overstate the scheme by twenty times.

**And read that $0.51bn as this draw's, not the model's.** Across ten seeds the
resource-cost line changes sign: the scheme lowers resource cost on some weather
sequences and raises it on others, and this one is among the favourable ones.
`ten_seeds.csv` beside this file is the envelope. A result that changes sign across
the seeds is not a result, and the reliability improvement, which is the more robust
of the two, is the one to lead with.

`dashboard.png` is the same paired run as eight panels: the fleet at the end, the
reliability outcome against the standard, price duration, every build against the
test it passed, the two cost views with the transfer between them named, what the
lane asked for and got, what consumers paid, and what a cap cost.

The most useful row is 2027, where both legs shed the same 28.3 GWh. The plant
awarded in 2026 has not been built yet. A procurement scheme is an instrument
about the future, and it cannot fix a year that arrives before its plant does.

Everything here is illustrative. The system is stylised and none of it is a
forecast.
