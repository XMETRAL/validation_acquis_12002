import sqlite3
from werkzeug.security import generate_password_hash

DB = r"C:\DEV\validation_acquis\Sites\pennylane\instance\validation.db"
EMAIL = "x.metral@axeinfo.fr"
NOUVEAU = "axe"

h = generate_password_hash(NOUVEAU, method="pbkdf2:sha256")
con = sqlite3.connect(DB)
n = con.execute("UPDATE user SET password_hash=? WHERE email=?", (h, EMAIL)).rowcount
con.commit(); con.close()
print(f"{n} compte(s) mis à jour dans {DB}")