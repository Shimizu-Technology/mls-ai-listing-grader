#!/usr/bin/env python3
import csv
import argparse
from dataclasses import dataclass

@dataclass
class Listing:
    listing_id: str
    price: float
    beds: int
    baths: int
    sqft: float
    dom: int
    condition: str
    remarks: str


def to_listing(row):
    return Listing(
        listing_id=row.get('ListingId', ''),
        price=float(row.get('ListPrice') or 0),
        beds=int(float(row.get('BedroomsTotal') or 0)),
        baths=int(float(row.get('BathroomsTotalInteger') or 0)),
        sqft=float(row.get('LivingArea') or 0),
        dom=int(float(row.get('DaysOnMarket') or 0)),
        condition=(row.get('PropertyCondition') or '').lower(),
        remarks=(row.get('PublicRemarks') or '').lower(),
    )


def ai_signals(remarks: str):
    risk = 0
    upside = 0
    risk_words = ['as-is', 'deferred maintenance', 'moisture', 'plumbing', 'foundation']
    upside_words = ['updated', 'renovated', 'move-in ready', 'rental potential']
    for w in risk_words:
        if w in remarks:
            risk += 1
    for w in upside_words:
        if w in remarks:
            upside += 1
    return risk, upside


def score(l: Listing):
    # deterministic base score
    s = 50.0

    # value-ish heuristics
    ppsf = (l.price / l.sqft) if l.sqft > 0 else 9999
    if ppsf < 260:
        s += 12
    elif ppsf < 320:
        s += 6

    # liquidity-ish heuristics
    if l.dom <= 21:
        s += 6
    elif l.dom <= 45:
        s += 3
    else:
        s -= 3

    # condition heuristics
    if l.condition in ['good', 'excellent']:
        s += 8
    elif l.condition in ['fair']:
        s -= 6

    # ai-assisted text flags
    risk, upside = ai_signals(l.remarks)
    s += upside * 2
    s -= risk * 2.5

    # clamp
    s = max(0, min(100, s))

    if s >= 75:
        bucket = 'schedule_visit'
    elif s >= 60:
        bucket = 'desk_review'
    else:
        bucket = 'skip'

    return round(s, 1), bucket, risk, upside


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', required=True)
    ap.add_argument('--top', type=int, default=5)
    args = ap.parse_args()

    listings = []
    with open(args.csv, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            listings.append(to_listing(row))

    ranked = []
    for l in listings:
        s, bucket, risk, upside = score(l)
        ranked.append((s, bucket, risk, upside, l))

    ranked.sort(key=lambda x: x[0], reverse=True)

    print('\nTop candidates:')
    for s, bucket, risk, upside, l in ranked[:args.top]:
        print(f"- {l.listing_id}: score={s} bucket={bucket} price=${int(l.price):,} dom={l.dom} risk={risk} upside={upside}")


if __name__ == '__main__':
    main()
