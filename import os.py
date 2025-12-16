import os

USERS_FILE = "users.txt"


def add_user(username):
    if not username:
        print("Username invalid!")
        return

    with open(USERS_FILE, "a") as f:
        f.write(username + "\n")

    print(f"Utilizatorul '{username}' a fost adăugat.")


def list_users():
    if not os.path.exists(USERS_FILE):
        print("Nu există utilizatori.")
        return

    with open(USERS_FILE, "r") as f:
        users = f.readlines()

    print("Lista utilizatorilor:")
    for user in users:
        print("- " + user.strip())


def find_user(username):
    if not os.path.exists(USERS_FILE):
        print("Fișierul de utilizatori nu există.")
        return

    with open(USERS_FILE, "r") as f:
        users = f.read()

    if username in users:
        print(f"Utilizatorul '{username}' a fost găsit.")
    else:
        print(f"Utilizatorul '{username}' NU a fost găsit.")


def main():
    while True:
        print("\n=== User Manager ===")
        print("1. Adaugă utilizator")
        print("2. Listează utilizatori")
        print("3. Caută utilizator")
        print("4. Ieșire")

        choice = input("Alege o opțiune: ")

        if choice == "1":
            username = input("Introdu username: ")
            add_user(username)

        elif choice == "2":
            list_users()

        elif choice == "3":
            username = input("Introdu username de căutat: ")
            find_user(username)

        elif choice == "4":
            print("La revedere!")
            break

        else:
            print("Opțiune invalidă!")


if __name__ == "__main__":
    main()
