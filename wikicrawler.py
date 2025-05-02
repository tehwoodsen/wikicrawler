from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import requests
import os
import re
import time
import getpass
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet

WIKI_API_URL = "https://en.wikipedia.org/w/api.php"

# === API FETCHING ===

def fetch_article(title):
    """Fetch the article content by title from Wikipedia API.
    
    Args:
        title (str): The title of the Wikipedia article.
        
    Returns:
        tuple: (article title, article content) if found, else (None, None).
    """
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "titles": title,
        "explaintext": True,
    }
    try:
        response = requests.get(WIKI_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"❌ Error fetching article '{title}': {e}")
        return None, None

    if "query" not in data or "pages" not in data["query"]:
        print(f"❌ Unexpected API response structure when fetching article '{title}'.")
        return None, None

    page = next(iter(data["query"]["pages"].values()))
    if "extract" in page and "title" in page:
        return page["title"], page["extract"]
    return None, None

def fetch_links(title):
    """Fetch internal links from the Wikipedia article.
    
    Args:
        title (str): The title of the Wikipedia article.
        
    Returns:
        list: List of linked article titles.
    """
    links = []
    plcontinue = None

    while True:
        params = {
            "action": "query",
            "format": "json",
            "prop": "links",
            "titles": title,
            "pllimit": "max",
        }
        if plcontinue:
            params["plcontinue"] = plcontinue

        try:
            response = requests.get(WIKI_API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            print(f"❌ Error fetching links for '{title}': {e}")
            break

        if "query" not in data or "pages" not in data["query"]:
            print(f"❌ Unexpected API response structure when fetching links for '{title}'.")
            break

        page = next(iter(data["query"]["pages"].values()))

        if "links" in page:
            # Exclude Help pages
            links.extend(link["title"] for link in page["links"] if not link["title"].startswith("Help:"))

        if "continue" in data and "plcontinue" in data["continue"]:
            plcontinue = data["continue"]["plcontinue"]
        else:
            break

    return links

# === FILE SAVING ===

def sanitize_filename(title):
    """Sanitize the filename by replacing non-alphanumeric characters with underscores."""
    safe_title = re.sub(r'[^A-Za-z0-9]+', '_', title).strip('_')
    return safe_title or "article"

def get_user_key():
    """Derive a cryptographic key from a user-supplied password using PBKDF2HMAC."""
    password = getpass.getpass("Enter password for key derivation: ").encode()
    salt = b'some_fixed_salt'  # In real use, use a secure random salt and store it
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(password))
    return key

def save_article(title, content, folder="articles", fmt="txt", fernet_key=None):
    """Save article content to a file in the specified format.
    
    Args:
        title (str): Article title.
        content (str): Article content.
        folder (str): Folder to save the file.
        fmt (str): File format ('txt', 'html', 'md').
        fernet_key (bytes or None): Encryption key for encrypting content.
    """
    safe_title = sanitize_filename(title)
    os.makedirs(folder, exist_ok=True)
    filename = os.path.join(folder, f"{safe_title}.{fmt}")

    if fmt == "html":
        content = f"<html><body><h1>{title}</h1><p>{content.replace(chr(10), '<br>')}</p></body></html>"
    elif fmt == "md":
        content = f"# {title}\n\n{content}"

    if fernet_key:
        content = Fernet(fernet_key).encrypt(content.encode()).decode()

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[✓] Saved article as '{filename}'")
    except OSError as e:
        print(f"❌ Error saving article '{title}': {e}")

# === MAIN LOGIC ===

def main():
    """Main program logic for crawling Wikipedia articles."""
    while True:
        subject = input("Enter a Wikipedia topic: ").strip()
        if subject:
            break
        print("❌ Topic cannot be empty. Please enter a valid Wikipedia topic.")

    title, content = fetch_article(subject)

    if not content:
        print("❌ Article not found.")
        return

    fmt = input("Choose a file format (txt/html/md) [txt]: ").strip().lower()
    if fmt not in ("txt", "html", "md"):
        fmt = "txt"

    folder = input("Enter folder name to save articles [articles]: ").strip()
    if not folder:
        folder = "articles"

    encrypt_choice = input("Would you like to encrypt the saved files? [y/N]: ").strip().lower()
    encrypt_files = encrypt_choice == 'y'

    fernet_key = get_user_key() if encrypt_files else None

    save_article(title, content, folder, fmt, fernet_key=fernet_key)

    links = fetch_links(title)
    print(f"[→] Found {len(links)} internal article links.")
    for link in links[:10]:  # Show first 10 as preview
        print(f"   - {link}")

    max_links_input = input("How many linked articles would you like to crawl? [default 50, max 100]: ").strip()
    try:
        max_links = min(100, max(1, int(max_links_input)))
    except ValueError:
        max_links = 50
    links = links[:max_links]

    choice = input("Would you like to crawl and save linked articles? [y/N]: ").strip().lower()
    if choice == "y":
        cpu_count = os.cpu_count() or 2
        if cpu_count < 4:
            max_threads = 2
        else:
            max_threads = min(10, cpu_count * 2)

        print(f"[ℹ️] Using up to {max_threads} threads for crawling.")

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = {executor.submit(fetch_article, link): link for link in links}
            for i, future in enumerate(
                tqdm(as_completed(futures), total=len(futures), desc="Crawling"), 1
            ):
                link = futures[future]
                try:
                    linked_title, linked_content = future.result()
                    if linked_content:
                        save_article(linked_title, linked_content, folder, fmt, fernet_key=fernet_key)
                except Exception as e:
                    print(f"[{i}/{len(links)}] ❌ Error fetching {link}: {e}")

if __name__ == "__main__":
    main()