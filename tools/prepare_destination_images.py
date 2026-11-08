"""Offline image audit/staging only. No uploads, requests, DB calls or source edits."""
from collections import defaultdict
from io import BytesIO
import hashlib
import json
from pathlib import Path
import warnings

from PIL import Image, ImageOps
from tools.local_destination_catalog import read_json, require, write_new

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'static/images/destinations'
STAGING = ROOT / 'local_catalog/image-staging'
MAX_SOURCE = 20 * 1024 * 1024
MAX_OUTPUT = 5 * 1024 * 1024
FORMATS = {'JPEG': ('jpg','image/jpeg'), 'PNG': ('png','image/png'), 'WEBP': ('webp','image/webp')}
# Explicit filename review proposals bound to the existing CSV record numbers.
# No fuzzy matching, image fetch, generated replacement or automatic assignment.
MAPPING = """1|EnchantedKingdom.jpg
2|NuvaliLakeSide.png
3|AyalaMallsSolenad.png
4|PaseoOutlets.jpg
5|SMCitySantaRosa.png
6|RobinsonsSantaRosa.jpg
7|VistaMallSantaRosa.jpeg
8|S&RMembershipShoppingNuvali.jpg
9|LandersSuperstoreNuvali.jpg
10|WalmartSantaRosa.jpg
11|BalibagoComplex.jpg
12|FortSantoDomingo_CuartelDeSantoDomingo.jpg
13|SantaRosaDeLimaParishChurch.jpg
14|TImezoneSolenad3.jpg
15|SMGameParkSantaRosa.jpg
16|McDonaldsNuvali.jpg
17|JollibeeBalibagoCrossing.jpg
18|JollibeeBalibagoComplex.jpg
19|JollibeeSantaRosaBayan.jpg
20|JollibeeGoldenCity.jpg
21|ChowkingSantaRosaBalibago.jpg
22|ChowkingSantaRosaBayan.jpg
23|BurgerKingSMSantaRosa.jpg
24|PizzaHutSMSantaRosa.png
25|NonosSMSantaRosa.png
26|IpponyariSantaRosa.jpg
27|PhoSaigonVietnameseRestaurantSantaRosa.jpg
28|TasteOfJoySantaRosa.png
29|ThreeMonkeysBrews&Bites.jpg
30|BadHCoffeeBarSpecialtyCoffee.jpg
31|UCCClockworkNuvali.png
32|AmareiLaCucinaNuvali.jpg
33|Ebi10.jpg
34|TheCaféMediterranean.jpg
35|ManamComfortFilipinoNuvali.jpg
36|TheMorningAfter.png
37|Nonna'sPasta&Pizzeria.png
38|BistroCharlemagne.jpg
39|Gerry'sGrillAyalaMallsSolenad.png
40|TGIFridaysNuvali.jpg
41|Bites&BarrelGastropub.jpg
42|SantaRosaArch.png
43|TheCityofSantaRosaMuseum(Museo de Santa Rosa).jpg
44|ArambuloAncestralHouse.jpg
45|ZavallaAncestralHouse.jpg
46|GonzalesAncestralHouse.jpg
47|ToyotaSantaRosa(Toyota Motor Philippines).jpg
48|Coca-ColaSantaRosa(Coca-Cola Beverages Philippines).jpg
49|MondeNissinSantaRosaPlant.jpg
50|MitsubishiMotorsPhilippinesCorporation.jpg
51|FunFarmSta.Elena.jpg
52|SantaRosaCityAuditorium.jpg
53|CityofSantaRosaMulti-PurposeComplex.jpg
54|LagunaCentral.jpg
55|YamazakiKitchenLaguna.jpg
56|NuvaliSandCourts.jpg
57|ACES Badminton and Pickleball Center - Santa Rosa, Laguna.jpg
58|WinnerBadmintonCourt.jpg
59|CourtZeroPickleballCourt.jpg
60|InfiniteBadminton&SportsCenter.jpg
61|Pickle G Society.jpg
62|TheCommonCourt.jpg
63|PicklePatio.jpg
64|TagapoBasketballCourt.jpg
68|SedaNuvali.jpg
69|TechnoparkHotel.jpg
79|Mariposa Budget Hotel Sta. Rosa.jpg
82|GoldenGateinn.jpg
83|Madie'sPlace.jpg
84|AmethystEconotel.jpeg
85|AsiatelEconoHotel.png
86|CalypsoResortHotel.jpg
87|LoloUwengChapel.jpg
88|KFCPaseodeSantaRosa.jpg
89|VctoryCentralMall.jpg
90|TargetMall.png
91|CafeMaestro.jpg
92|CafeRoyal.jpg
93|CafeDeRosa.jpg
94|CafeAmelia.jpg
95|KafeLando.jpg
96|IslandFoodPark.jpg
97|GrillYard.jpeg
98|MaryGrace.jpg"""


def sanitize(raw):
    require(0 < len(raw) <= MAX_SOURCE, 'Invalid local source-image size.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(BytesIO(raw)) as image:
            fmt, size = image.format, image.size
            require(fmt in FORMATS and size[0] * size[1] <= 20_000_000 and max(size) <= 8192
                    and getattr(image, 'n_frames', 1) == 1, 'Unsupported local still-image format/dimensions.')
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            oriented = ImageOps.exif_transpose(image)
            pixels = oriented.convert('RGB' if fmt == 'JPEG' else 'RGBA')
            clean = Image.new(pixels.mode, pixels.size)
            clean.paste(pixels)
            output = BytesIO()
            clean.save(output, format=fmt, **({'quality':85} if fmt in ('JPEG','WEBP') else {}))
    content = output.getvalue()
    require(len(content) <= MAX_OUTPUT, 'Derived photo exceeds the unchanged 5MiB upload limit.')
    return content, FORMATS[fmt][0], FORMATS[fmt][1], size


def main():
    plan_path = ROOT / 'local_catalog/production-mapped-publication-v3.review.json'
    plan = read_json(plan_path)
    mapping = {int(line.split('|',1)[0]):line.split('|',1)[1] for line in MAPPING.splitlines()}
    require(len(mapping)==84 and len(set(mapping.values()))==84, 'Duplicate mapping or file.')
    files = {p.name:p for p in SOURCE.iterdir() if p.is_file()}
    require(set(files)==set(mapping.values()), 'Image inventory changed; review extra/missing files before staging.')
    before = {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}
    STAGING.mkdir(exist_ok=True)
    require(STAGING.resolve().parent==(ROOT/'local_catalog').resolve(), 'Staging path escapes review directory.')
    prepared = {}; duplicates=defaultdict(list)
    for name,path in files.items():
        require(not path.is_symlink() and path.resolve().parent==SOURCE.resolve(), 'Unexpected linked image path.')
        raw = path.read_bytes()
        content,extension,mimetype,size = sanitize(raw)
        digest = hashlib.sha256(content).hexdigest()
        output = STAGING/(digest+'.'+extension)
        if output.exists():
            require(hashlib.sha256(output.read_bytes()).hexdigest()==digest,'Staging file changed.')
        else:
            with output.open('xb') as stream:stream.write(content)
        issues=[]
        if len(raw)>MAX_OUTPUT:issues.append('original_over_5MiB_derived_copy_prepared')
        if path.suffix.lower().lstrip('.') not in ({'jpg','jpeg'} if extension=='jpg' else {extension}):
            issues.append('original_extension_mismatch_derived_extension_corrected')
        duplicates[before[name]].append(name)
        prepared[name]=dict(source_file=str(path.relative_to(ROOT)),source_sha256=before[name],source_bytes=len(raw),
            staged_file=str(output.relative_to(ROOT)),staged_sha256=digest,staged_bytes=len(content),
            mime_type=mimetype,original_width=size[0],original_height=size[1],issues=issues)
    records=[]
    for entry in plan['records']:
        number=entry['csv_record'];filename=mapping.get(number)
        current=entry['original_row']['image_url'] if entry['original_row'] else None
        image=prepared.get(filename)
        held=number in (56,58)
        notes=[]
        if number==56:notes.append('Visual inspection shows indoor badminton, not the CSV outdoor sand-court category. Do not use for this record.')
        if number==58:notes.append('Identical bytes to #56. Venue identity remains unconfirmed; no automatic assignment.')
        if number==10:notes.append('Filename says Walmart; image visibly says WalterMart/Sta. Rosa. Confirm branch identity; this does not verify coordinates.')
        if number in (32,41,89):notes.append('Filename spelling differs from destination; confirm mapping before use.')
        records.append(dict(csv_record=number,name=entry['name'],existing_id=entry['existing_id'],existing_image_url=current,
            candidate=image,proposed_action='preserve_existing_image' if current else (
                'hold_for_identity_review' if held else 'attach_only_after_separate_image_approval' if image else 'leave_image_null'),
            source_mapping_approved=False,visual_identity_confirmed=False,notes=notes,
            publication_location_status=entry['final_status_proposal'],ready_to_upload=False,proposed_hosted_image_url=None))
    require(before=={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}, 'Original image bytes changed.')
    result=dict(review_only=True,hosted_changes=0,target_project_ref=plan['target_project_ref'],
        plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),source_images_preserved=True,
        file_count=len(files),csv_records=len(records),records_without_local_image=[r['csv_record'] for r in records if r['candidate'] is None],
        identical_source_groups=[names for names in duplicates.values() if len(names)>1],
        preserved_existing_image_count=sum(bool(r['existing_image_url']) for r in records),
        source_hashes=before,records=records,
        integration='Review/stage for the existing guarded Admin Storage upload and audited image_url mutation; do not loosen URL validation or use owner DML. No upload mechanism is executed here.')
    write_new(ROOT/'local_catalog/destination-images.review.json',result)
    print(json.dumps({k:result[k] for k in ('file_count','csv_records','records_without_local_image','identical_source_groups','preserved_existing_image_count','source_images_preserved')},ensure_ascii=True,indent=2))


if __name__=='__main__':main()
