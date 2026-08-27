"""Ten documents. In memory, because a corpus on disk would be a second thing
to explain and this example is about the answers, not the store."""

from __future__ import annotations

DOCUMENTS: dict[str, str] = {
    "hours": (
        "The reading room is open Monday to Friday, 9:00 to 19:00, and on "
        "Saturday morning from 9:00 to 13:00. It is closed on Sundays."
    ),
    "cards": (
        "A reader's card is free for residents and costs 12 EUR a year for "
        "everyone else. Bring an identity document to the desk."
    ),
    "loans": (
        "Members may borrow six items at a time for twenty-eight days. Loans "
        "renew twice online unless another reader has reserved the item."
    ),
    "fines": (
        "There is no fine for a late return. After sixty days the item is "
        "invoiced at its replacement cost."
    ),
    "rooms": (
        "Two study rooms seat six people each. They are booked at the desk or "
        "by telephone, up to two weeks ahead."
    ),
    "wifi": (
        "Wifi is open and needs no password. The network is called "
        "BIBLIO-OPEN and sessions last four hours."
    ),
    "printing": (
        "Printing costs 10 cents a page in black and 40 in colour, paid at "
        "the machine with a card."
    ),
    "children": (
        "The children's section is on the ground floor. Story hour is every "
        "Wednesday at 17:00 for ages four to eight."
    ),
    "donations": (
        "Book donations are accepted on Tuesday and Thursday mornings. We can "
        "take up to two boxes per household per month."
    ),
    "contact": (
        "Write to the desk for anything else; the librarians answer within two "
        "working days."
    ),
}
