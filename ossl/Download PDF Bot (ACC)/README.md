## DownloadBot

This small script logs into the OTITHEE Accounting Department Portal and
downloads all **Over 25 Lakh Transaction** invoices in one go.

### Setup

1. **Create and activate a virtual environment (optional but recommended):**

```bash
cd /home/needyamin/Desktop/DownloadBot
python3 -m venv .venv
source .venv/bin/activate
```

2. **Install dependencies:**

```bash
pip install -r requirements.txt
```

### Usage

Run the bot with:

```bash
python3 /home/needyamin/Desktop/DownloadBot/downloadBot.py
```

The script will:

- Open Chrome.
- Log into [`https://acc.otithee.com/login`](https://acc.otithee.com/login) with the configured credentials.
- Go to [`https://acc.otithee.com/invoice-generate/over-25-lakh`](https://acc.otithee.com/invoice-generate/over-25-lakh).
- Find every `Invoice` download button (e.g. links like
  `https://acc.otithee.com/invoice-download-over25/01711395909`) and open them
  so the browser downloads each invoice.

All downloaded files will be saved under:

```bash
/home/needyamin/Desktop/DownloadBot/downloads
```


