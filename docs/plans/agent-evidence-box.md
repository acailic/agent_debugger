# Agent Evidence Box

**Predlog plana za 11. novembar 2026.** Cilj je za 4–6 inženjerskih nedelja isporučiti pilot za jedan kontrolisani MCP tok. Auditor treba da može da proveri paket dokaza offline, a operater da iz istog zapisa otvori istragu u Peaky Peek-u.

## Prvi slučaj upotrebe

B2B tim koji razvija agente za osiguranje već ima MCP alat koji menja status predmeta. Za pilot koristiti staging sa sintetičkim predmetima i jednim dozvoljenim alatom. Platform ili security lead uvodi gateway, a osoba iz interne revizije prima paket i proverava ga na drugom računaru. Pitanje koje moraju da razreše je koji je workload zatražio promenu, koja je politika važila, šta je alat vratio i da li je istorija tog izvršavanja potpuna u okviru nadziranog toka.

Predložena poruka za kupca: **„Proverite šta je agent uradio kroz vaše MCP alate i otvorite isti događaj u istrazi incidenta.“** Hipoteza je da zajednički tok za proveru dokaza, analizu i replay skraćuje istragu dovoljno da opravda kupovinu.

## Dokazi i konkurencija

- Qin i saradnici pokazali su da testirani lokalni agenti mogu da manipulišu sopstvenim tragovima i preporučili presretanje izvan kontrole agenta. *Agent Flight Recorder* prikazuje strukturisane zapise, hash lanac i Merkle grupe. AIVS i Agent Audit Trail su Internet-Draft predlozi za interoperabilnost. [Qin i saradnici](https://arxiv.org/abs/2609.30266) · [Agent Flight Recorder](https://arxiv.org/abs/2609.01931) · [AIVS](https://datatracker.ietf.org/doc/draft-stone-aivs/) · [Agent Audit Trail](https://datatracker.ietf.org/doc/draft-sharif-agent-audit-trail/)
- Obsign dokumentuje MCP gateway, zapečaćene zapise i offline proveru paketa. Golem dokumentuje potpisane i ulančane zapise za coding agente. U prvoj nedelji uporediti isti slučaj sa Obsign-om i postojećim procesom kupca, po pokrivenosti, vremenu ugradnje, vremenu istrage i upotrebljivosti izvoza. Rezultat tog poređenja određuje da li graditi gateway, integrisati postojeći recorder ili zaustaviti razvoj. [Obsign](https://github.com/obsign/obsign) · [Golem](https://docs.golem.team/guides/audit-trail)
- EU AI Act propisuje mogućnost automatskog beleženja za visokorizične sisteme i uređuje čuvanje zapisa pod kontrolom pružaoca ili korisnika sistema. GDPR propisuje odgovornost i dokazivost poštovanja načela, među kojima su minimizacija podataka i ograničenje čuvanja. Pilot daje dokaz za konkretne kontrole i omogućava kupcu da utvrdi primenljivost i rok čuvanja za svoj slučaj. [EU AI Act, čl. 12, 19 i 26](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng) · [GDPR, čl. 5](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng)

## Granica poverenja

| Pristup | Pokrivenost i trošak |
| --- | --- |
| Potpisivanje pri postojećem SDK ingest-u | Najbrže za integraciju. Dokazuje integritet primljenih zapisa od trenutka prijema. Izbor događaja ostaje u procesu agenta. |
| Gateway na putu do MCP alata | Nezavisno beleži pozive za alate koje infrastruktura stavlja iza gateway-a. Zahteva kontrolu pristupa ciljnom servisu i uvodi latenciju. **Izbor za pilot.** |
| Izolovani runtime sa nadzorom mreže i procesa | Može da proširi pokrivenost na shell, fajlove i direktne API pozive. Traži dodatne integracije po okruženju i ima smisla kada kupci potvrde potrebu. |

Agent koristi autentifikovan MCP endpoint u odvojenom servisu. Gateway ima sopstveni identitet, skladište, konfiguraciju i ključ. Ciljni servis prihvata mutacije samo od identiteta gateway-a. Gateway evidentira identitet dobijen iz autentifikacije i koristi ID izvršavanja koji izdaje kontrolisani servis. Korelacija sa SDK sesijom služi navigaciji kroz istragu. Zapis iz SDK-a zadržava deklarisani izvor.

Paket dokazuje šta je gateway primio, odlučio, prosledio i koju je potvrdu dobio, u granicama deklarisanog MCP toka. Shell, lokalni fajlovi, pozivi modelu i direktni pozivi drugim servisima su van opsega pilota. Potvrda gateway-a svedoči o odgovoru alata. Za potvrdu stvarne promene stanja proverava se i zapis ciljnog sistema. Gateway, ključ i verifikator su deo granice poverenja. Nezavisni checkpoint čuva dokaz o ranije potvrđenom stanju lanca ako naknadno postane sporan.

## Tok od poziva do paketa

1. **Pre prosleđivanja.** Gateway trajno upisuje zahtev i odluku `allow` ili `deny`, sa pouzdanim identitetom, ID-jem poziva, vremenom gateway-a i verzijom pravila. Ako trajni upis ne uspe, zahtev se odbija. Gateway vezuje naziv i šemu alata za odobreni identitet servera i konfiguraciju verzije. Promena šeme traži eksplicitno odobrenje. MCP anotacije služe kao opisni metapodaci. [MCP o pouzdanosti anotacija](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/)
2. **Posle prosleđivanja.** Gateway trajno upisuje opaženi ishod pre nego što ga vrati klijentu. Prekid posle prosleđivanja može ostaviti ishod `unknown`. Takav poziv se usaglašava sa zapisom ciljnog sistema, uz stabilan ID poziva i idempotency key koji ciljni alat podržava. Gateway izbegava automatsko ponavljanje mutacija čiji je ishod nepoznat. Stanje i istorija pokušaja ostaju vidljivi posle restarta.
3. **Potpisivanje i čuvanje.** Verziona JSON šema ima monotoni redni broj po izvršavanju, `prev_hash`, ID gateway-a i `key_id`. Koristiti kanonski JSON, SHA-256 lanac i Ed25519 iz održavanih biblioteka. Dodela rednog broja, upis potpisanog događaja i pomeranje vrha lanca moraju biti atomski i pri paralelnim pozivima. Podrazumevani zapis sadrži dozvoljenu listu metapodataka i kod ishoda. Argumenti i rezultati se podrazumevano izostavljaju, a eventualna dozvoljena polja prolaze redakciju pre potpisa, skladištenja i izvoza. [RFC 8785](https://www.rfc-editor.org/info/rfc8785) · [RFC 8032](https://www.rfc-editor.org/info/rfc8032)
4. **Nezavisna potvrda.** Odvojeno skladište pod kontrolom audit tima prima zapis o početku izvršavanja pre prvog prosleđenog poziva i potpisani završni checkpoint sa brojem događaja i završnim hashom. Auditor pribavlja očekivani ID i checkpoint iz tog skladišta. Time može da uoči izostavljen očekivani paket ili skraćenje lanca. Ako završna potvrda nedostaje, paket ostaje označen kao nepotpun, uz prikaz integriteta dostupnih zapisa i nepoznatih ishoda.
5. **Isporuka auditoru.** Paket sadrži `manifest.json`, `events.ndjson`, potpis i opis pokrivenosti. Zasebno distribuiran CLI proverava paket offline prema unapred potvrđenom javnom ključu i nezavisno pribavljenom checkpoint-u. Prikazuje odvojene rezultate za integritet, pokrivenost izvršavanja i poznatost ishoda. Nepoznat ključ ili neusklađen hash daju neuspešnu proveru. Kupac upravlja registrom javnih ključeva, uključujući prethodne javne ključeve za proveru istorijskih paketa posle rotacije.

## Ugradnja u Peaky Peek

- **Recorder i verifikator** imaju zaseban format i životni ciklus. Postojeći [SDK događaji](../../agent_debugger_sdk/core/events/) i [collector ingest](../../collector/server.py) služe dijagnostici. Dokaz nastaje na gateway-u, izvan SDK ingest putanje.
- **Adapter za istragu** preslikava proverene događaje u timeline, uz `run_id`, `call_id`, provereni izvor i referencu na original. [Audit API](../../api/audit_routes.py) i [AuditPanel](../../frontend/src/components/AuditPanel.tsx) prikazuju dokaz za događaj. Rezultat kriptografske provere i postojeća ocena ponašanja prikazuju se kao odvojena polja. Pilot koristi postojeći pregled i restore kada postoji odgovarajući checkpoint. Simulirani replay može da koristi fiksne rezultate sintetičkog alata. Šira podrška za simulaciju i nastavak izvršavanja zavisi od [W04](../ROADMAP.md#W04--From-inspection-to-controlled-replay-experiments).
- **Privatnost i prenosivost.** Proveriti primenu postojeće [redakcije](../../redaction/pipeline.py) na adapter i koristiti metapodatke iz potpisane reprezentacije u prikazu. Rok čuvanja paketa i potvrda dogovara se za pilot. Definisati mapiranje na AAT/AIVS i vezu preko OTel identifikatora u skladu sa [W07](../ROADMAP.md#W07--Framework-fidelity-and-open-interoperability). Prva isporuka je paket i CLI. Merkle dokazi za parcijalne izvoze, dodatni transporti i OEM distribucija slede na osnovu potražnje.

## Redosled isporuke

| Period | Isporuka | Uslov za nastavak |
| --- | --- | --- |
| Nedelja 1 | Jedan sintetički tok, definisana granica poverenja, uzorak audit paketa, poređenje sa Obsign-om i 3–5 razgovora sa timovima koji već koriste MCP. | Jedan tim potvrđuje da može da stavi alat iza gateway-a i da će uključiti platform inženjera i audit korisnika u pilot. |
| Nedelje 2–3 | MCP gateway za jedan klijent i jedan server, uz jednu dogovorenu verziju protokola i transport. Pokriti otkrivanje alata, `tools/call`, trajni upis pre i posle poziva, potpis, nezavisnu potvrdu, izvoz i offline CLI. | Svaka kontrolisana promena stanja ima prethodni trajni zapis. CLI otkriva očekivane greške integriteta i prikazuje nepoznat ishod kad potvrda nedostaje. |
| Nedelje 4–6 | Povezivanje sa AuditPanel-om, demonstracija istrage i vremenski ograničen staging pilot. | Auditor samostalno proverava paket i nalazi odgovarajući događaj. Kupac potvrđuje merljivu korist i prihvata plaćeni sledeći korak. |

### Kriterijumi za pilot

- Na unapred definisanom skupu staging poziva uporediti gateway sa nezavisnim zapisom ciljnog servisa. Cilj je 100% promena iz nadziranog toka sa prethodnim trajnim zapisom. Uključiti dozvoljen poziv, odbijen poziv, ponovljeni zahtev i prekide pre i posle prosleđivanja. Proveriti da infrastruktura odbija pristup alatu iz identiteta agenta i da retry sa istim ključem ne duplira mutaciju.
- Verifikator mora da otkrije izmenu, umetanje, duplikat, promenu redosleda, brisanje događaja i skraćenje paketa na sintetičkim kopijama. Obuhvatiti i izostavljen paket za poznati ID, odsustvo nezavisnog checkpoint-a i nepoznat ključ. Proveriti izvoz, aplikativne logove i skladište sa sintetičkim tajnama i ličnim podacima.
- Početni ciljevi su dodatnih ≤ 50 ms na p95 u staging-u pri dogovorenom opterećenju i ≥ 30% kraće vreme za odgovor na isto audit pitanje uz jednaku tačnost. Meriti odvojeno latenciju gateway-a i ciljnog alata, te vreme istrage u postojećem procesu i uz Evidence Box. Ciljevi su radne pretpostavke koje pilot treba da potvrdi.

## Komercijalna odluka

Prvi model je plaćeni self-hosted pilot sa jednim tokom i fiksnim obimom. Za kupca su predmet kupovine proverljiv izvoz i brža istraga. Ako kupac već koristi Obsign ili sličan recorder, prvo testirati uvoz dokaza i istragu. Ako nijedan tim ne može da uvede gateway niti ima izvor potpisanih dokaza, zaustaviti razvoj posle prve nedelje i vratiti se razgovorima sa kupcima. Nakon uspešnog pilota testirati godišnju licencu po kontrolisanom okruženju. OEM za observability platforme otvoriti nakon dva ponovljiva uvođenja sa istim formatom i potvrđene potražnje za integracijom.
