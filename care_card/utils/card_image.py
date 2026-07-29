# Copyright (c) 2026, Kreatao and contributors
"""Server side SVG rendering of the virtual card (no external dependency)."""

import frappe
from frappe.utils import get_url

from care_card.utils.formatting import fmt_date


def _esc(text):
	text = "" if text is None else str(text)
	return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
		.replace('"', "&quot;"))


def _qr_matrix_placeholder(token, size=21):
	"""Deterministic visual block derived from the token.

	A real QR is rendered client side by the portal (qrcode.js). This block is a
	stable server side stand-in so the SVG card is self contained and printable.
	"""
	import hashlib

	digest = hashlib.sha256((token or "").encode("utf-8")).digest()
	bits = []
	while len(bits) < size * size:
		for byte in digest:
			for i in range(8):
				bits.append((byte >> i) & 1)
		digest = hashlib.sha256(digest).digest()
	return [bits[r * size:(r + 1) * size] for r in range(size)]


def render_card_svg(card, beneficiary=None, token=None):
	tier = frappe.get_cached_doc("Care Card Tier", card.tier)
	colour = tier.card_colour or "#C9A227"
	accent = tier.card_accent or "#7A6212"
	name = beneficiary.dependent_name if beneficiary else card.member_name
	code = beneficiary.beneficiary_code if beneficiary else card.card_number
	number = " ".join([card.card_number[i:i + 4] for i in range(0, len(card.card_number or ""), 4)])

	matrix = _qr_matrix_placeholder(token or card.card_number)
	cell = 4.2
	qr_cells = []
	for r, row in enumerate(matrix):
		for c, bit in enumerate(row):
			if bit:
				qr_cells.append(
					'<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="#111"/>'
					% (470 + c * cell, 118 + r * cell, cell, cell)
				)

	return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 340" width="600" height="340" role="img" aria-label="Care Card">
	<defs>
		<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
			<stop offset="0%" stop-color="{colour}"/>
			<stop offset="100%" stop-color="{accent}"/>
		</linearGradient>
	</defs>
	<rect width="600" height="340" rx="22" fill="url(#bg)"/>
	<rect x="14" y="14" width="572" height="312" rx="16" fill="#ffffff" opacity="0.95"/>
	<text x="40" y="62" font-family="Helvetica,Arial,sans-serif" font-size="13" letter-spacing="3" fill="{accent}">CARE CARD</text>
	<text x="40" y="96" font-family="Helvetica,Arial,sans-serif" font-size="30" font-weight="700" fill="#111">{tier}</text>
	<text x="40" y="150" font-family="Helvetica,Arial,sans-serif" font-size="12" fill="#6b6b6b">MEMBER</text>
	<text x="40" y="174" font-family="Helvetica,Arial,sans-serif" font-size="20" fill="#111">{name}</text>
	<text x="40" y="212" font-family="Helvetica,Arial,sans-serif" font-size="12" fill="#6b6b6b">CARD NUMBER</text>
	<text x="40" y="238" font-family="Courier,monospace" font-size="20" letter-spacing="2" fill="#111">{number}</text>
	<text x="40" y="276" font-family="Helvetica,Arial,sans-serif" font-size="12" fill="#6b6b6b">BENEFICIARY</text>
	<text x="40" y="296" font-family="Courier,monospace" font-size="14" fill="#111">{code}</text>
	<text x="250" y="276" font-family="Helvetica,Arial,sans-serif" font-size="12" fill="#6b6b6b">VALID UNTIL</text>
	<text x="250" y="296" font-family="Helvetica,Arial,sans-serif" font-size="14" fill="#111">{expiry}</text>
	<rect x="464" y="112" width="104" height="104" rx="6" fill="#ffffff" stroke="#e3e3e3"/>
	{qr}
	<text x="464" y="234" font-family="Helvetica,Arial,sans-serif" font-size="9" fill="#8a8a8a">Present at the counter</text>
</svg>""".format(
		colour=_esc(colour),
		accent=_esc(accent),
		tier=_esc((card.tier or "").upper()),
		name=_esc(name),
		number=_esc(number),
		code=_esc(code),
		expiry=_esc(fmt_date(card.expiry_date)),
		qr="".join(qr_cells),
	)


def card_url(card):
	return get_url("/my-card?card=%s" % (card.card_number or card.name))
