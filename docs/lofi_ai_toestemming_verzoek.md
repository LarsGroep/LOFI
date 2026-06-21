# Verzoek om schriftelijke toestemming — inzet AI/LLM en sub-verwerkers

**Aan:** Life Over Future B.V. (Lofi), t.a.v. dhr. D. Grootendorst
**Van:** Team Armadillo — [naam student], UvA Master Challenge "From Spreadsheet to Smart System"
**Datum:** [datum]
**Betreft:** Toestemming op grond van de Verwerkersovereenkomst, art. 3.4, 3.5 en Bijlage 2

---

Geachte heer Grootendorst,

In het kader van het Project ontwikkelen wij een AI-agent die het boekingsteam
helpt bij het beoordelen en vinden van artiesten. Voor dit onderdeel willen wij,
conform **art. 3.5** en **Bijlage 2** van de Verwerkersovereenkomst, gegevens laten
verwerken door een externe AI-/LLM-dienst, en conform **art. 3.4** enkele
sub-verwerkers inzetten. Dat mag uitsluitend met uw **voorafgaande, uitdrukkelijke
schriftelijke toestemming**. Met deze brief vragen wij die toestemming, onder de
hieronder genoemde waarborgen.

## Waarvoor wij toestemming vragen

| Dienst / sub-verwerker | Rol in het Project | Waarborgen die wij instellen |
|---|---|---|
| **Anthropic (Claude API)** — AI/LLM | Redeneerlaag van de agent (rationales, vergelijkingen, Q&A). Tevens als ontwikkelhulpmiddel tijdens de bouw. | • **Geen training** op of hergebruik van onze invoer (commerciële API-voorwaarden) • **Zero-data-retention** waar beschikbaar • **Verwerking binnen de EER** (EU data residency, art. 3.7) • **Data-minimalisatie**: alleen de strikt noodzakelijke velden (zie onder) • Verwerkersovereenkomst/DPA van Anthropic op verzoek bijgevoegd |
| **Supabase** — database | Opslag van scraper-/Chartmetric-data en scores | EER-regio (art. 3.7); toegang op need-to-know |
| **Airtable** — read-only | Inlezen van historische boekingsdata ter verrijking van de analyses (conform Bijlage 1: afgeschermde, read-only kopie) | Uitsluitend **lezen**; geen wegschrijven zonder uw aparte opdracht |

## Welke gegevens naar de AI/LLM-dienst gaan (data-minimalisatie)

Standaard **uitsluitend**: artiestennaam, genres, de berekende scores, de
groeivoorspelling en geaggregeerde, publieke platformcijfers (bijv. Spotify-
luisteraars). **Niet** meegestuurd, tenzij u dit expliciet toestaat:

- **Gages en andere vertrouwelijke bedrijfsgegevens.** Deze zijn waardevol om
  aanbevelingen te onderbouwen ("vergelijkbaar met een eerdere boeking"), maar het
  zijn vertrouwelijke gegevens. Wij sturen ze alleen naar de AI/LLM-dienst als u
  daar uitdrukkelijk toestemming voor geeft; anders blijven ze uitsluitend binnen
  het dashboard.
- Ticketverkoop- of bezoekersgegevens op individueel niveau.
- Bijzondere categorieën persoonsgegevens (worden sowieso niet verwerkt).

## Onze toezeggingen

- Verwerking en opslag uitsluitend binnen de **EER** (art. 3.7).
- Geen hergebruik/training van ingevoerde gegevens door de AI/LLM-dienst (art. 3.5).
- Toegang op **need-to-know**; geheimhouding conform art. 5.
- **Verwijdering** van alle (kopieën van) gegevens uiterlijk 14 dagen na afronding
  van het Project (art. 10), met schriftelijke bevestiging op verzoek.

## Toestemming

Door ondertekening verleent Lofi toestemming voor de inzet van bovengenoemde
diensten als sub-verwerkers in de zin van art. 3.4, en voor de verwerking door de
genoemde AI/LLM-dienst in de zin van art. 3.5 / Bijlage 2, onder de genoemde
waarborgen.

☐ Toestemming verleend, inclusief het meesturen van gage-/boekingsgegevens naar de AI/LLM-dienst
☐ Toestemming verleend, **zonder** gage-/boekingsgegevens naar de AI/LLM-dienst (alleen dashboard-zijde)

Namens Lofi: ______________________  D. Grootendorst   Datum: __________

---

*Dit verzoek is opgesteld door team Armadillo voor het Project en bevat geen
juridisch advies. Bevestig de exacte voorwaarden van Anthropic/Supabase/Airtable
aan de hand van hun verwerkersovereenkomsten (DPA's).*
