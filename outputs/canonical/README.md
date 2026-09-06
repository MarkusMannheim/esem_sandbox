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

**And read that $0.51bn as this draw's, not the model's.** `ten_seeds.csv` beside
this file is ten seeds of the same comparison. The scheme improves reliability in
eight of them and lowers the total resource cost in four, and the outage it avoids
is small, positive and steady while fuel, fixed costs and capital swing four times
as far and decide the sign.

Sorted by the demand growth path each run drew, the swing is not random: on the
three low-growth draws the scheme is worse by $2.0bn to $4.4bn and avoids no outage
at all, and on both high-growth draws it is better and avoids the most. A scheme's
worth depends on which future the market turned out to be in, and this seed is a
high-growth one.

`dashboard.png` is the same paired run as eight panels: the fleet at the end, the
reliability outcome against the standard, price duration, every build against the
test it passed, the two cost views with the transfer between them named, what the
lane asked for and got, what consumers paid, and what a cap cost.

The most useful row is 2027, where both legs shed the same 28.3 GWh. The plant
awarded in 2026 has not been built yet. A procurement scheme is an instrument
about the future, and it cannot fix a year that arrives before its plant does.

Everything here is illustrative. The system is stylised and none of it is a
forecast.
