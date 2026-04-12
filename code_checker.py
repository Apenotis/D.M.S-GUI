import subprocess
import sys
import os

# Wir definieren jetzt die Ziele: Die start.py und den kompletten dms_core Ordner
TARGETS = ["start.py", "dms_core/"]

def run_tool(command_list, tool_name):
    print(f"\n{'='*60}")
    print(f" 🛡️  Starte {tool_name}...")
    print(f"{'='*60}\n")
    
    try:
        # Wir hängen die Ziele (start.py und dms_core) an die Befehle an
        full_command = command_list + TARGETS
        result = subprocess.run(full_command, capture_output=True, text=True)
        
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip())
            
        if result.returncode == 0:
            print(f"\n[OK] {tool_name} hat keine kritischen Fehler gefunden.")
        else:
            print(f"\n[INFO] {tool_name} hat Hinweise gefunden (siehe oben).")
            
    except FileNotFoundError:
        print(f"[FEHLER] '{command_list[0]}' nicht gefunden. Bitte installiere es via pip.")
        # Wir beenden hier nicht, damit die anderen Tools noch laufen können
    except Exception as e:
        print(f"[FEHLER] Ein unerwarteter Fehler ist aufgetreten: {e}")

def main():
    print("🚀 D.M.S. ULTIMATIVE CODE-ANALYSE")
    print("Überprüfe: start.py und den dms_core Ordner...\n")
    
    # 1. isort: Bringt Ordnung in die Import-Hierarchie aller Dateien
    run_tool([sys.executable, "-m", "isort"], "isort (Import Sortierer)")
    
    # 2. Black: Der "gnadenlose" Formatter für einheitliches Design
    run_tool([sys.executable, "-m", "black"], "Black (Code Formatter)")
    
    # 3. Flake8: Der Inspektor für Logik-Sünden
    # Wir ignorieren E501 (Zeilenlänge), da wir Black vertrauen
    run_tool([sys.executable, "-m", "flake8", "--extend-ignore=E501"], "Flake8 (Linter)")
    
    # 4. Vulture: Findet "toten Code", der nur Platz wegnimmt
    # Wir setzen die Min-Confidence etwas höher, damit er nicht zu streng ist
    run_tool([sys.executable, "-m", "vulture", "--min-confidence", "80"], "Vulture (Dead Code Finder)")
    
    # 5. Radon: Die "Schulnoten" für die Komplexität deines Codes
    run_tool([sys.executable, "-m", "radon", "cc", "-s", "-a"], "Radon (Komplexitäts-Noten)")
    
    print("\n" + "="*60)
    print("✨ ANALYSE BEENDET! Dein modulares System ist jetzt klinisch rein.")
    print("="*60)
    input("\nDrücke ENTER zum Beenden...")

if __name__ == "__main__":
    main()