from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AppSettings,
    FlavorTag,
    Grinder,
    PresetGrinderRange,
    RecipePreset,
)

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
