import dms_core.database as db
import dms_core.config as cfg
from dms_core.utils import tracker  # Import before using the decorator.


@tracker  # Safe to use after the import above.
def load_maps() -> dict[int, list]:
    """
    Load maps from the database and sort them.
    Favorites come first, while Heretic and Hexen entries stay grouped.
    """
    blocks: dict[int, list] = {1: [], 2: [], 3: []}

    try:
        maps = db.get_all_maps()
        for row in maps:
            item = [
                str(row.get("Cleared", "0")).strip(),
                str(row.get("NoMods", "0")).strip(),
                str(row.get("ID", "")).strip(),
                str(row.get("Name", "")).strip(),
                str(row.get("IWAD", "")).strip(),
                str(row.get("Path", "")).strip(),
                str(row.get("MOD", "0")).strip(),
                str(row.get("ARGS", "0")).strip(),
                str(row.get("Kategorie", "PWAD")).strip().upper(),
                str(row.get("Playtime", "0")).strip(),
                str(row.get("LastPlayed", "-")).strip(),
                str(row.get("RemoteID", "0")).strip(),
                str(row.get("Favorite", "0")).strip(),
            ]
            if not item[2]:
                continue

            kat = item[8]
            if kat == "IWAD":
                blocks[1].append(item)
            elif kat == "PWAD":
                blocks[2].append(item)
            else:
                blocks[3].append(item)

        def get_sort_key(m):
            iwad = str(m[4]).strip().lower()
            fav = m[12] == "0"

            group = 4
            if "hexen" in iwad:
                group = 2
            elif "heretic" in iwad:
                group = 1
            elif "strife" in iwad:
                group = 3

            return (fav, group, m[3].lower())

        blocks[1].sort(key=lambda x: (x[12] == "0", x[3].lower()))
        blocks[2].sort(key=lambda x: (x[12] == "0", x[3].lower()))
        blocks[3].sort(key=get_sort_key)

        if blocks[3]:
            formatted = []
            last_g = None
            for itm in blocks[3]:
                iwad = str(itm[4]).strip().lower()

                if "hexen" in iwad:
                    curr_g = "HEXEN"
                elif "heretic" in iwad:
                    curr_g = "HERETIC"
                elif "strife" in iwad:
                    curr_g = "STRIFE"
                else:
                    curr_g = "REST"

                if last_g is not None and curr_g != last_g:
                    formatted.append([""] * 13)
                formatted.append(itm)
                last_g = curr_g
            blocks[3] = formatted

        return blocks
    except Exception as e:
        print(f"Loader error: {e}")
        return blocks