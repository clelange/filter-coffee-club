from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import utcnow
from .demo import DEMO_PIN, DEMO_PROFILE_NAMES
from .models import (
    AppSettings,
    Brew,
    BrewFilter,
    Coffee,
    Dripper,
    FlavorTag,
    Grinder,
    PresetGrinderRange,
    Profile,
    Rating,
    RecipePreset,
)
from .security import hash_pin

PRESETS = [
    ("Light washed / floral / acidic", 16.5, 94, 96, 28, 31),
    ("Light natural / fruity", 16, 93, 95, 29, 33),
    ("Medium washed / balanced", 16, 92, 95, 30, 34),
    ("Medium natural / anaerobic", 15.5, 91, 94, 31, 35),
    ("Chocolate / nutty medium-dark", 15.5, 90, 93, 32, 35),
    ("Dark roast", 15, 88, 91, 33, 36),
    ("Old / faded beans", 15, 90, 93, 30, 34),
]

FLAVORS = {
    "Floral": ["Floral", "Jasmine"],
    "Fruity": [
        "Berry",
        "Grape",
        "Citrus",
        "Stone fruit",
        "Tropical fruit",
        "Apple / pear",
        "Dried fruit",
    ],
    "Sweet": ["Honey", "Caramel / brown sugar", "Vanilla"],
    "Nutty / cocoa": ["Nutty", "Almond", "Chocolate / cocoa"],
    "Spice": ["Cinnamon", "Brown spice"],
    "Roasted": ["Toasted", "Cereal / malty", "Smoky"],
    "Fermented": ["Winey", "Fermented"],
    "Green / earthy": ["Herbal / tea-like", "Green / vegetative", "Earthy", "Woody / papery"],
}


def seed_database(db: Session) -> None:
    if db.get(AppSettings, 1) is None:
        db.add(AppSettings(id=1))

    grinder = db.scalar(
        select(Grinder).where(Grinder.manufacturer == "Comandante", Grinder.model == "C40")
    )
    if grinder is None:
        grinder = Grinder(
            manufacturer="Comandante",
            model="C40",
            setting_unit="clicks",
            setting_step=1,
            soft_min=0,
            soft_max=50,
            guidance=(
                "Count clicks outward from click zero. Values outside the range are "
                "allowed with a warning."
            ),
        )
        db.add(grinder)
        db.flush()

    for index, (name, ratio, temp_min, temp_max, click_min, click_max) in enumerate(PRESETS):
        preset = db.scalar(select(RecipePreset).where(RecipePreset.name == name))
        if preset is None:
            preset = RecipePreset(
                name=name,
                ratio=ratio,
                temperature_min_c=temp_min,
                temperature_max_c=temp_max,
                sort_order=index,
            )
            db.add(preset)
            db.flush()
            db.add(
                PresetGrinderRange(
                    preset_id=preset.id,
                    grinder_id=grinder.id,
                    setting_min=click_min,
                    setting_max=click_max,
                )
            )

    for parent_index, (parent_name, children) in enumerate(FLAVORS.items()):
        parent = db.scalar(
            select(FlavorTag).where(FlavorTag.parent_id.is_(None), FlavorTag.name == parent_name)
        )
        if parent is None:
            parent = FlavorTag(name=parent_name, sort_order=parent_index)
            db.add(parent)
            db.flush()
        for child_index, child_name in enumerate(children):
            child = db.scalar(
                select(FlavorTag).where(
                    FlavorTag.parent_id == parent.id, FlavorTag.name == child_name
                )
            )
            if child is None:
                db.add(
                    FlavorTag(
                        name=child_name,
                        parent_id=parent.id,
                        sort_order=child_index,
                    )
                )
    db.commit()


def seed_demo_database(db: Session) -> None:
    """Create a fictional, useful dataset only in a completely unconfigured database."""

    if (db.scalar(select(func.count(Profile.id))) or 0) > 0:
        return

    now = utcnow()
    shared_pin_hash = hash_pin(DEMO_PIN)
    profiles = [
        Profile(
            display_name=name,
            pin_hash=shared_pin_hash,
            role="admin" if name == DEMO_PROFILE_NAMES[0] else "member",
            pin_change_required=False,
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=30),
        )
        for name in DEMO_PROFILE_NAMES
    ]
    db.add_all(profiles)
    db.flush()

    grinder = db.scalar(
        select(Grinder).where(Grinder.manufacturer == "Comandante", Grinder.model == "C40")
    )
    natural_preset = db.scalar(
        select(RecipePreset).where(RecipePreset.name == "Light natural / fruity")
    )
    washed_preset = db.scalar(
        select(RecipePreset).where(RecipePreset.name == "Light washed / floral / acidic")
    )
    assert grinder is not None and natural_preset is not None and washed_preset is not None

    drippers = [
        Dripper(
            manufacturer="Hario",
            model="V60 02",
            notes="Conical demo dripper",
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=30),
        ),
        Dripper(
            manufacturer="Orea",
            model="V4 Wide",
            notes="Flat-bottom demo dripper",
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=30),
        ),
    ]
    filters = [
        BrewFilter(
            name="V60 paper 02",
            notes="White tabbed paper",
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=30),
        ),
        BrewFilter(
            name="Flat-bottom fast flow",
            notes="Demo wave-style paper",
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=30),
        ),
    ]
    db.add_all([*drippers, *filters])
    db.flush()

    coffee_rows = [
        {
            "roaster": "Sample Roastery",
            "name": "Ethiopia Halo Beriti",
            "country": "Ethiopia",
            "region": "Yirgacheffe",
            "producer": "Example Smallholders",
            "process": "Washed",
            "roast_level": "Light",
            "variety": "Heirloom",
            "package_notes": "Jasmine, bergamot, peach",
        },
        {
            "roaster": "Sample Roastery",
            "name": "Colombia Las Flores",
            "country": "Colombia",
            "region": "Huila",
            "producer": "Demo Cooperative",
            "process": "Natural",
            "roast_level": "Light",
            "variety": "Caturra",
            "package_notes": "Strawberry, cacao, panela",
        },
        {
            "roaster": "Imaginary Coffee Lab",
            "name": "Kenya Kirinyaga AA",
            "country": "Kenya",
            "region": "Kirinyaga",
            "producer": "Example Washing Station",
            "process": "Washed",
            "roast_level": "Light",
            "variety": "SL28, SL34",
            "package_notes": "Blackcurrant, grapefruit, brown sugar",
        },
        {
            "roaster": "Imaginary Coffee Lab",
            "name": "Brazil Serra Doce",
            "country": "Brazil",
            "region": "Minas Gerais",
            "producer": "Demo Estate",
            "process": "Pulped natural",
            "roast_level": "Medium",
            "variety": "Yellow Bourbon",
            "package_notes": "Hazelnut, chocolate, dried cherry",
        },
    ]
    coffees = []
    for index, values in enumerate(coffee_rows):
        age = 20 - index * 3
        coffee = Coffee(
            **values,
            roast_date=(now - timedelta(days=age + 8)).date(),
            opened_date=(now - timedelta(days=age)).date(),
            created_by_id=profiles[0].id,
            created_at=now - timedelta(days=age),
            updated_at=now - timedelta(days=age),
        )
        coffees.append(coffee)
    db.add_all(coffees)
    db.flush()

    brew_specs = [
        (0, 0, 0, 0, washed_preset, 15.0, 250.0, 95.0, 29.0, 185),
        (1, 1, 1, 1, natural_preset, 15.5, 250.0, 93.0, 31.0, 198),
        (2, 2, 0, 0, washed_preset, 16.0, 260.0, 94.0, 30.0, 192),
        (3, 3, 1, 1, natural_preset, 16.0, 250.0, 91.0, 33.0, 176),
        (0, 1, 0, 0, washed_preset, 15.0, 240.0, 96.0, 28.0, 202),
        (1, 2, 1, 1, natural_preset, 15.5, 255.0, 92.0, 32.0, 188),
        (2, 3, 0, 0, washed_preset, 16.0, 256.0, 93.0, 31.0, 181),
        (3, 0, 1, 1, natural_preset, 15.0, 240.0, 90.0, 34.0, 169),
        (0, 2, 0, 0, washed_preset, 15.5, 250.0, 95.0, 29.0, 190),
        (1, 3, 1, 1, natural_preset, 16.0, 260.0, 93.0, 31.0, 194),
        (2, 0, 0, 0, washed_preset, 15.0, 245.0, 94.0, 30.0, 183),
        (3, 1, 1, 1, natural_preset, 15.5, 248.0, 91.0, 33.0, 174),
    ]
    brews: list[Brew] = []
    for index, spec in enumerate(brew_specs):
        (
            coffee_index,
            operator_index,
            dripper_index,
            filter_index,
            preset,
            dose,
            water,
            temperature,
            setting,
            duration,
        ) = spec
        completed_at = now - timedelta(days=12 - index, hours=index % 4)
        brew = Brew(
            coffee_id=coffees[coffee_index].id,
            operator_id=profiles[operator_index].id,
            grinder_id=grinder.id,
            dripper_id=drippers[dripper_index].id,
            filter_id=filters[filter_index].id,
            source_preset_id=preset.id,
            dose_g=dose,
            water_g=water,
            temperature_c=temperature,
            grinder_setting=setting,
            servings=1,
            target_flow_g_s=4.5,
            total_brew_time_s=duration,
            bloom_water_g=round(dose * 3),
            bloom_time_s=35,
            pour_count=3 if dripper_index == 0 else 2,
            technique_note="Demo brew with evenly spaced pours.",
            status="completed",
            rating_token=f"demo-rating-{index + 1:02d}",
            completed_at=completed_at,
            created_at=completed_at - timedelta(minutes=duration / 60),
            updated_at=completed_at,
        )
        brews.append(brew)
    db.add_all(brews)
    db.flush()

    tag_by_name = {
        tag.name: tag
        for tag in db.scalars(select(FlavorTag).where(FlavorTag.parent_id.is_not(None)))
    }
    rating_patterns = [
        (8, 4, 1, 4, 2, ("Jasmine", "Citrus")),
        (7, 3, 2, 4, 3, ("Berry", "Caramel / brown sugar")),
        (9, 4, 1, 5, 2, ("Grape", "Citrus")),
        (6, 2, 3, 3, 4, ("Chocolate / cocoa", "Nutty")),
        (8, 4, 1, 4, 2, ("Stone fruit", "Honey")),
        (7, 3, 2, 4, 3, ("Tropical fruit", "Vanilla")),
    ]
    for brew_index, brew in enumerate(brews):
        for offset in range(3):
            profile = profiles[(brew_index + offset) % len(profiles)]
            pattern = rating_patterns[(brew_index + offset) % len(rating_patterns)]
            rating = Rating(
                brew_id=brew.id,
                profile_id=profile.id,
                liking=pattern[0],
                acidity=pattern[1],
                bitterness=pattern[2],
                sweetness=pattern[3],
                body=pattern[4],
                created_at=brew.completed_at + timedelta(minutes=offset + 2),
                updated_at=brew.completed_at + timedelta(minutes=offset + 2),
            )
            rating.flavor_tags = [tag_by_name[name] for name in pattern[5]]
            db.add(rating)

    db.commit()
