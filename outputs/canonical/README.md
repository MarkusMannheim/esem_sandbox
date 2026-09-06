# Canonical outputs

Committed so a talk never depends on live compute, a working network or a
conference wifi connection. Regenerate with:

```bash
esem-sandbox run --out outputs/canonical
esem-sandbox compare --ticks 20 --seed 20260904 --out outputs/canonical
python tools/ten_seeds.py outputs/canonical/ten_seeds.csv 20
```

`comparison.csv` and `comparison.txt` are one paired run: twenty years, one seed,
both legs on the same weather sequence. Read the two cost lines together. The
scheme moves the bill DOWN by $21.06bn and the resource cost UP by $0.40bn, and
the $21.46bn between them is a transfer from generators to consumers rather than a
saving by anybody. On this seed the bill would not merely overstate the scheme, it
would report a cost as a benefit.

Underneath the total, the scheme avoids $2.07bn of outage and spends $2.47bn more
on fuel, fixed costs and capital to do it. Whether that trade is worth taking is a
question about the value of lost load, which is a regulatory figure here and not a
measurement.

**And read all of that as this draw's, not the model's.** `ten_seeds.csv` beside
this file is ten seeds of the same comparison. The scheme improves reliability in
six of them and makes it worse in four; it lowers the total resource cost in four.
Both the outage line and the cost line change sign across the seeds, so neither
number above is a property of the scheme.

What does travel is the sort. Taken by the demand growth path each run drew, on the
three low-growth draws the scheme avoids no outage at all, costs $1.2bn to $5.7bn
more, and leaves reliability slightly worse; on the two high-growth draws it avoids
the largest outages in the set, $1.64bn and $2.07bn. It awards around 13,000 MW on
the fast draws and around 8,000 MW on the slow ones, so it is responding to the
future it is in - it just responds to a future it only half knows. This seed is a
high-growth one, which is why it is the flattering end of the range.

`dashboard.png` is the same paired run as eight panels: the fleet at the end, the
reliability outcome against the standard, price duration, every build against the
test it passed, the two cost views with the transfer between them named, what the
lane asked for and got, what consumers paid, and what a cap cost.

The most useful row is 2027, where both legs shed the same 28.3 GWh, 18.9 times the
standard. The plant awarded in 2026 has not been built yet. A procurement scheme is
an instrument about the future, and it cannot fix a year that arrives before its
plant does. That row is identical on both legs no matter which seed you run.

Everything here is illustrative. The system is stylised and none of it is a
forecast.
