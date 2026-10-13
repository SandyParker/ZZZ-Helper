import os
import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv
from collections import Counter

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

ARMORER_CHARACTERS = {
    "Claret": {"desc": "Electric Armorer Agent", "passive": 30.0, "base_def": 441}
}

AGENT_ID_TO_NAME = {
    "1611": "Claret",
}

ENGINES = {
    14161: {"name": "Crimson Thirst", "base_def": 431, "def_pct": 48, "crit_rate": 25, "crit_rate_per_upgrade": 2.5},
    13022: {"name": "Candlelight Conspiracy", "base_def": 356, "def_pct": 40, "crit_rate": 8, "crit_rate_per_upgrade": 2.3},
    13021: {"name": "Bloodmarrow Coffer", "base_def": 356, "def_pct": 0, "crit_rate": 20, "crit_rate_per_upgrade": 0},
    13017: {"name": "Catty Luck", "base_def": 356, "def_pct": 40, "crit_rate": 0, "crit_rate_per_upgrade": 0},
}

PROPERTY_MAP = {
    13103: ("flat_def", 1.0),
    13102: ("def_pct", 0.01),
    20103: ("crit_rate", 0.01),
    21103: ("crit_dmg", 0.01),
}

ENKA_API_URL = "https://enka.network/api/zzz/uid/{uid}/"

DISC_SET_NAMES = {
    "342": "Thorned Rose",
    "327": "Branch & Blade Song",
    "310": "Woodpecker Electro",
    "311": "Puffer Electro"
}


class ArmorerSelect(discord.ui.Select):
    def __init__(self, armorers_data: dict[str, dict], nickname: str):
        self.armorers_data = armorers_data
        self.nickname = nickname
        options = [
            discord.SelectOption(
                label=name,
                description=data.get("desc", "Armorer Agent"),
                default=False
            )
            for name, data in armorers_data.items()
        ]
        super().__init__(
            placeholder="Select an Armorer character...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_name = self.values[0]
        char_data = self.armorers_data[selected_name]

        equipped = char_data.get("EquippedList", [])
        disc_groups = Counter()
        for item in equipped:
            eq = item.get("Equipment", {})
            disc_id = str(eq.get("Id", ""))
            if len(disc_id) >= 3:
                group = disc_id[:3]
                disc_groups[group] += 1

        weapon_data = char_data.get("Weapon", {})
        engine_id = weapon_data.get("Id")
        upgrade_level = weapon_data.get("UpgradeLevel", 1)
        engine = ENGINES.get(engine_id, {})

        char_base_def = ARMORER_CHARACTERS.get(selected_name, {}).get("base_def", 0)
        engine_base_def = engine.get("base_def", 0)
        engine_def_pct = engine.get("def_pct", 0)
        engine_crit_rate = engine.get("crit_rate", 0)
        engine_crit_rate_upgrade = engine.get("crit_rate_per_upgrade", 0) * (upgrade_level - 1)

        total_flat_def = 0
        total_def_pct = 0
        total_crit_rate = 0
        total_crit_dmg = 0

        for item in equipped:
            eq = item.get("Equipment", {})
            level = eq.get("Level", 0)
            for prop in eq.get("MainPropertyList", []):
                pid = prop.get("PropertyId")
                pval = prop.get("PropertyValue", 0)
                if pid in PROPERTY_MAP:
                    stat, mult = PROPERTY_MAP[pid]
                    value = pval * 4 * mult
                    if stat == "flat_def":
                        total_flat_def += value
                    elif stat == "def_pct":
                        total_def_pct += value
                    elif stat == "crit_rate":
                        total_crit_rate += value
                    elif stat == "crit_dmg":
                        total_crit_dmg += value
            for prop in eq.get("RandomPropertyList", []):
                pid = prop.get("PropertyId")
                pval = prop.get("PropertyValue", 0)
                plevel = prop.get("PropertyLevel", 0)
                if pid in PROPERTY_MAP:
                    stat, mult = PROPERTY_MAP[pid]
                    value = pval * plevel * mult
                    if stat == "flat_def":
                        total_flat_def += value
                    elif stat == "def_pct":
                        total_def_pct += value
                    elif stat == "crit_rate":
                        total_crit_rate += value
                    elif stat == "crit_dmg":
                        total_crit_dmg += value

        set_342 = disc_groups.get("342", 0) + disc_groups.get("343", 0)
        set_327 = disc_groups.get("327", 0)
        set_310 = disc_groups.get("310", 0)

        if set_342 >= 2:
            total_def_pct += 16

        base_def = char_base_def + engine_base_def
        total_def_pct += engine_def_pct
        final_def = base_def * (1 + total_def_pct / 100) + total_flat_def

        crit_rate = 33.8
        crit_dmg = 50.0

        passive_crit = ARMORER_CHARACTERS.get(selected_name, {}).get("passive", 0)
        crit_rate += passive_crit + engine_crit_rate + engine_crit_rate_upgrade + total_crit_rate

        if set_342 >= 4:
            if final_def >= 1800:
                crit_rate += 16
            elif final_def >= 1000:
                crit_rate += 8
        if set_327 >= 2:
            crit_dmg += 16
        if set_310 >= 2:
            crit_rate += 8

        crit_dmg += total_crit_dmg

        final_score = crit_rate + crit_dmg * 0.35

        CR_RATE_PER_ROLL = 2.4
        CR_DMG_PER_ROLL = 4.8
        CR_DMG_EFFECTIVE = CR_DMG_PER_ROLL * 0.35

        display_name = self.nickname if self.nickname else "Unknown"
        lines = [f"**{display_name} - {selected_name}**"]
        for group, count in sorted(disc_groups.items()):
            set_name = DISC_SET_NAMES.get(group, "Unknown")
            lines.append(f"  **{set_name} ({group})**: {count} piece(s)")

        engine_name = engine.get("name", f"Unknown ({engine_id})")
        lines.append(f"\n**Engine:** {engine_name} (Overclock: {upgrade_level})")
        lines.append(f"**Base DEF:** {base_def:.1f}")
        lines.append(f"**Total DEF%:** {total_def_pct:.1f}%")
        lines.append(f"**Total Flat DEF:** {total_flat_def:.1f}")
        lines.append(f"**Final DEF:** {final_def:.1f}")
        lines.append(f"\n**Base CRIT Rate:** 33.8%")
        lines.append(f"**Passive CRIT Rate:** +{passive_crit:.1f}%")
        lines.append(f"**Engine CRIT Rate:** +{engine_crit_rate + engine_crit_rate_upgrade:.1f}%")
        lines.append(f"**Disc CRIT Rate:** +{total_crit_rate:.1f}%")
        lines.append(f"**Set Bonuses CRIT Rate:** +{crit_rate - 33.8 - passive_crit - engine_crit_rate - engine_crit_rate_upgrade - total_crit_rate:.1f}%")
        lines.append(f"**Total CRIT Rate:** **{crit_rate:.1f}%**")
        lines.append(f"\n**Base CRIT DMG:** 50.0%")
        lines.append(f"**Disc CRIT DMG:** +{total_crit_dmg:.1f}%")
        lines.append(f"**Set Bonuses CRIT DMG:** +{crit_dmg - 50.0 - total_crit_dmg:.1f}%")
        lines.append(f"**Total CRIT DMG:** **{crit_dmg:.1f}%**")
        lines.append(f"\n**Final Score - CRIT Rate + (CRIT DMG × 0.35):** **{final_score:.1f}**")

        if final_score < 200:
            needed = 200 - final_score
            lines.append(f"\n**Rolls needed to reach 200%:** {needed:.1f}%")
            lines.append("```")
            lines.append(f"{'CR Rolls':>8} | {'CD Rolls':>8} | {'Total %':>8}")
            lines.append("-" * 30)
            found = False
            for cr_rolls in range(0, 10):
                for cd_rolls in range(0, 10):
                    gained = cr_rolls * CR_RATE_PER_ROLL + cd_rolls * CR_DMG_EFFECTIVE
                    if gained >= needed:
                        lines.append(f"{cr_rolls:>8} | {cd_rolls:>8} | {gained:>7.1f}%")
                        found = True
                        break
                if found and cr_rolls > 0:
                    break
            lines.append("```")
        else:
            lines.append(f"\n**Already above 200%!**")

        await interaction.response.edit_message(
            content="\n".join(lines),
            view=None
        )


class ArmorerView(discord.ui.View):
    def __init__(self, armorers_data: dict[str, dict], nickname: str):
        super().__init__(timeout=60)
        self.add_item(ArmorerSelect(armorers_data, nickname))


class ZZZHelper(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        await self.tree.sync()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    async def fetch_enka_data(self, uid: str) -> dict | None:
        if not self.session:
            return None
        try:
            async with self.session.get(ENKA_API_URL.format(uid=uid), timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            pass
        return None

    def get_armorers_data(self, enka_data: dict) -> tuple[dict[str, dict], str]:
        armorers = {}
        nickname = ""
        try:
            player_info = enka_data.get("PlayerInfo", {})
            social = player_info.get("SocialDetail", {})
            profile = social.get("ProfileDetail", {})
            nickname = profile.get("Nickname") or profile.get("Nickname", "")

            showcase = player_info.get("ShowcaseDetail", {})
            avatar_list = showcase.get("AvatarList", [])
            for avatar in avatar_list:
                agent_id = str(avatar.get("Id", ""))
                name = AGENT_ID_TO_NAME.get(agent_id)
                if name and name in ARMORER_CHARACTERS:
                    armorers[name] = avatar
        except Exception:
            pass
        return armorers, nickname


bot = ZZZHelper()


@bot.tree.command(
    name="armorercr",
    description="Calculate Armorer Crit Rate from your UID"
)
@app_commands.describe(
    uid="Your ZZZ UID"
)
async def armorercr(interaction: discord.Interaction, uid: str):
    await interaction.response.defer(thinking=True)

    enka_data = await bot.fetch_enka_data(uid)
    if not enka_data:
        await interaction.followup.send(
            f"Failed to fetch data for UID `{uid}`. Make sure it's correct and your profile is public."
        )
        return

    armorers_data, nickname = bot.get_armorers_data(enka_data)
    if not armorers_data:
        await interaction.followup.send(f"No Armorer characters found for UID `{uid}`.")
        return

    view = ArmorerView(armorers_data, nickname)

    display_name = nickname if nickname else "Unknown"
    content = (
        f"**Armorer Crit Rate Calculator**\n"
        f"UID: `{uid}` | User: **{display_name}**\n"
        f"Found: {', '.join(armorers_data.keys())}\n"
        f"Select a character to view their Drive Discs:"
    )
    await interaction.followup.send(content=content, view=view)


if not TOKEN:
    raise RuntimeError("Missing DISCORD_BOT_TOKEN in .env")
print("Token: " + TOKEN)
bot.run(TOKEN)