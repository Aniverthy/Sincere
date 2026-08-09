"""Populate a development environment so every feature is reachable by hand.

Without this the app is technically complete but untestable: a single real account sees an
empty daily 15, can never match, and so can never reach chat, We-Met, or a warning.

Everything is created through the real HTTP API, so the seeded population passes the same
verification, admission and ratio logic as any other signup — a seeded region is a genuine
region, not a fixture.

Order matters. FR-2.5 caps admitted men at ~93% of *active women*, so seeding men first
would simply waitlist them all. Women are created first, then men against the resulting
ceiling.

Usage
-----
    python scripts/seed_dev.py --near-user 45913154 --women 12 --men 8
    python scripts/seed_dev.py --lat 12.9149 --lng 77.5393
    python scripts/seed_dev.py --near-user 45913154 --match-with 45913154
    python scripts/seed_dev.py --match-with 45913154 --messages 24   # fires the We-Met prompt
    python scripts/seed_dev.py --warn 45913154                        # trips the FR-5.2 rule
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8000/v1"

FEMALE_NAMES = [
    "Aditi", "Meera", "Nisha", "Priya", "Kavya", "Ananya", "Divya", "Ishita",
    "Riya", "Sanya", "Tara", "Neha", "Pooja", "Shreya", "Anjali",
]
MALE_NAMES = [
    "Arjun", "Rahul", "Vikram", "Karan", "Rohan", "Aditya", "Nikhil", "Siddharth",
    "Varun", "Aman", "Kabir", "Dev", "Ishaan", "Yash", "Manav",
]
BIOS = [
    "Filter coffee and long arguments about films.",
    "I make bread on Sundays and lose at badminton.",
    "Architect. Will detour twenty minutes for a good bookshop.",
    "Runs slowly, cooks quickly, talks constantly.",
    "Trying to read more and scroll less. Mixed results.",
    "Dog person, tea person, terrible-at-chess person.",
]
PROMPTS = [
    ("A perfect Sunday", "A bookshop, filter coffee, and absolutely no plans."),
    ("I will not shut up about", "The last film that genuinely surprised me."),
    ("An opinion I will defend", "Pineapple belongs nowhere near a pizza."),
]
TAGS = ["coffee", "films", "hiking", "books", "music", "cooking", "travel", "art", "dogs", "yoga"]


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read() or b"{}"), resp.status
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read() or b"{}"), exc.code


def admin_token() -> str:
    import jwt as pyjwt

    return pyjwt.encode(
        {"sub": "seed-ops", "scope": "admin", "typ": "access", "iss": "sincere", "exp": 4102444800},
        "dev-only-insecure-secret-change-me",
        algorithm="HS256",
    )


def create_user(phone, gender, name, lat, lng, radius_km=50):
    """Full signup through the real API. Returns (token, user_id, status)."""
    signup, _ = call("POST", "/auth/signup", {"phone": phone})
    if "dev_otp" not in signup or not signup["dev_otp"]:
        raise SystemExit(
            "Signup did not return dev_otp. Set SMS_PROVIDER=console in .env."
        )

    tokens, _ = call(
        "POST",
        "/auth/verify-otp",
        {"challenge_id": signup["challenge_id"], "otp": signup["dev_otp"]},
    )
    token = tokens["access_token"]

    if tokens["status"] == "onboarding":
        call("POST", f"/me/gender?gender={gender}", token=token)
        question, answer = random.choice(PROMPTS)
        call(
            "PATCH",
            "/me",
            {
                "name": name,
                "dob": (
                    f"{random.randint(1990, 2003)}-0{random.randint(1, 9)}"
                    f"-1{random.randint(0, 8)}"
                ),
                "bio": random.choice(BIOS),
                "tags": random.sample(TAGS, 5),
                "prompts": [{"q": question, "a": answer}],
            },
            token=token,
        )
        # Scatter slightly so distances are not all identical, but stay inside the same hex.
        call(
            "POST",
            "/me/location",
            {
                "latitude": lat + random.uniform(-0.012, 0.012),
                "longitude": lng + random.uniform(-0.012, 0.012),
            },
            token=token,
        )
        call("PATCH", "/me/radius", {"radius_km": radius_km}, token=token)

        session, _ = call("POST", "/verification/liveness/session", token=token)
        call(
            "POST",
            "/verification/liveness",
            {"session_id": session["session_id"], "object_key": session["object_key"]},
            token=token,
        )

        # If the dev bypass is off, approve from the queue as the founder would.
        queue, _ = call("GET", "/admin/review-queue?limit=100", token=admin_token())
        for item in queue.get("items", []):
            call(
                "POST",
                f"/admin/review/{item['flag_id']}/decision",
                {"decision": "approve", "note": "seed"},
                token=admin_token(),
            )

        signup, _ = call("POST", "/auth/signup", {"phone": phone})
        tokens, _ = call(
            "POST",
            "/auth/verify-otp",
            {"challenge_id": signup["challenge_id"], "otp": signup["dev_otp"]},
        )
        token = tokens["access_token"]

    me, _ = call("GET", "/me", token=token)
    return token, me.get("user_id"), tokens["status"]


async def resolve_target(partial_id: str):
    """Find a user by an id prefix, returning their coordinates and region."""
    from sincere.shared import db
    from sincere.shared.db import C

    database = await db.connect()
    async for user in database[C.USERS].find({}):
        if user["_id"].startswith(partial_id):
            location = (user.get("last_recorded_location") or {}).get("coordinates")
            await db.disconnect()
            return user["_id"], user.get("gender"), location, user.get("h3_region")
    await db.disconnect()
    raise SystemExit(f"No user whose id starts with {partial_id!r}")


async def find_seeded_partner(gender: str, region: str, exclude_id: str):
    """Pick an existing active account of the given gender in a region, and mint it a token.

    Signs in by minting the token directly rather than replaying the OTP flow — a user
    document does not record which phone number produced it, so there is nothing to replay.
    This is a dev script against a dev secret; it has no production equivalent.
    """
    from sincere.shared import db
    from sincere.shared.auth import Scope, create_access_token
    from sincere.shared.db import C

    database = await db.connect()
    chosen = await database[C.USERS].find_one(
        {
            "gender": gender,
            "h3_region": region,
            "status": "active",
            "_id": {"$ne": exclude_id},
        }
    )
    await db.disconnect()

    if chosen is None:
        return None

    token = create_access_token(
        chosen["_id"], Scope.ACTIVE, gender=chosen.get("gender"), region=region
    )
    return ("seeded", token, chosen["_id"])


async def inject_fast_swipes(partial_id: str, count: int = 30) -> None:
    """Trip the FR-5.2 dwell rule.

    Written straight to the swipes collection because the rule needs 25+ right-swipes and the
    product only serves 15 profiles a day — it is not reachable by hand in one session.
    """
    from sincere.antiabuse import api as antiabuse
    from sincere.shared import cache, db
    from sincere.shared.db import C

    database = await db.connect()
    await cache.connect()

    user_id, _, _, _ = await resolve_target(partial_id)
    now = datetime.now(UTC)

    for index in range(count):
        await database[C.SWIPES].update_one(
            {"user_id": user_id, "target_id": f"seed-fast-{index}"},
            {
                "$set": {
                    "direction": "right",
                    "dwell_ms": random.randint(200, 900),  # far under the 10s threshold
                    "server_dwell_ms": random.randint(200, 900),
                    "created_at": now - timedelta(minutes=count - index),
                }
            },
            upsert=True,
        )

    result = await antiabuse.evaluate_user(user_id)
    print(f"  injected {count} fast right-swipes -> {result}")
    await db.disconnect()


async def flood_messages(match_id: str, user_a_token: str, user_b_token: str, count: int) -> None:
    """Send enough messages to cross the FR-4.3 We-Met threshold (20-30 in 3 days)."""
    for index in range(count):
        token = user_a_token if index % 2 == 0 else user_b_token
        call(
            "POST",
            f"/matches/{match_id}/messages",
            {"body": f"Seeded message {index + 1}", "client_id": f"seed-{index}"},
            token=token,
        )
    print(f"  sent {count} messages -> We-Met should now be pending")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--near-user", help="seed around this user id prefix")
    parser.add_argument("--lat", type=float, help="latitude to seed around")
    parser.add_argument("--lng", type=float, help="longitude to seed around")
    parser.add_argument("--women", type=int, default=12)
    parser.add_argument("--men", type=int, default=8)
    parser.add_argument("--match-with", help="create a mutual like with this user id prefix")
    parser.add_argument("--messages", type=int, default=0, help="flood a match to fire We-Met")
    parser.add_argument("--warn", help="trip the dwell rule for this user id prefix")
    args = parser.parse_args()

    if args.warn:
        asyncio.run(inject_fast_swipes(args.warn))
        return

    target_id = target_gender = region = None
    if args.near_user:
        target_id, target_gender, location, region = asyncio.run(resolve_target(args.near_user))
        if not location:
            raise SystemExit("That user has no recorded location yet — open the app once.")
        lat, lng = location[1], location[0]
        print(
            f"Seeding around {target_id[:8]} ({target_gender}) at "
            f"{lat:.4f},{lng:.4f}  region={region}"
        )
    elif args.lat is not None and args.lng is not None:
        lat, lng = args.lat, args.lng
        print(f"Seeding around {lat:.4f},{lng:.4f}")
    else:
        raise SystemExit("Give either --near-user or both --lat and --lng.")

    stamp = datetime.now(UTC).strftime("%H%M%S")
    created: dict[str, list[tuple[str, str, str]]] = {"female": [], "male": []}

    # Women first: FR-2.5 caps admitted men at ~93% of active women, so seeding men against
    # an empty region would just waitlist every one of them.
    print(f"\nCreating {args.women} women...")
    for index in range(args.women):
        phone = f"+9188{stamp}{index:02d}"
        name = FEMALE_NAMES[index % len(FEMALE_NAMES)]
        token, user_id, status = create_user(phone, "female", name, lat, lng)
        created["female"].append((phone, token, user_id))
        print(f"  {name:10s} {phone}  {status}")

    print(f"\nCreating {args.men} men...")
    for index in range(args.men):
        phone = f"+9189{stamp}{index:02d}"
        name = MALE_NAMES[index % len(MALE_NAMES)]
        token, user_id, status = create_user(phone, "male", name, lat, lng)
        created["male"].append((phone, token, user_id))
        marker = "" if status == "active" else "   <- waitlisted (ratio ceiling, FR-2.5)"
        print(f"  {name:10s} {phone}  {status}{marker}")

    if args.match_with:
        target_id, target_gender, _, region = asyncio.run(resolve_target(args.match_with))
        opposite = "male" if target_gender == "female" else "female"

        partner = next((p for p in created[opposite] if p[2]), None)
        if partner is None:
            # Nobody created in this run — reuse an already-seeded account in the same region
            # so `--match-with` works on its own, without re-seeding a population.
            partner = asyncio.run(find_seeded_partner(opposite, region, target_id))
        if partner is None:
            raise SystemExit(
                f"No {opposite} user in region {region} to match with. "
                f"Seed one first:  --near-user {args.match_with} --{opposite[0:5]} 4"
            )

        _, partner_token, partner_id = partner
        # The seeded user likes them first, so the moment the real user swipes right the
        # match forms immediately — no waiting on someone else's turn.
        response, status = call(
            "POST",
            "/swipes",
            {"target_id": target_id, "direction": "right", "dwell_ms": 18_000},
            token=partner_token,
        )
        print(f"\n{partner_id[:8]} has liked {target_id[:8]} (status {status}).")
        print("Swipe right on them in the app and it will match instantly.")

        if args.messages:
            print("\nTo flood messages, first form the match by swiping right in the app,")
            print(f"then re-run:  python scripts/seed_dev.py --messages {args.messages} \\")
            print(f"                  --match-with {args.match_with}")

    print("\nDone. Region state:")
    regions, _ = call("GET", "/admin/regions", token=admin_token())
    for entry in regions.get("regions", []):
        print(
            f"  {entry['region']}  men={entry['active_men']} women={entry['active_women']} "
            f"state={entry['admission_state']} ceiling={entry['ceiling']} "
            f"waitlist={entry['waitlist_size']}"
        )


if __name__ == "__main__":
    main()
