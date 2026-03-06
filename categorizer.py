import re

CURRENCY_CONFIG = {
    "IN": {"symbol": "₹", "code": "INR", "label": "India (₹)", "k": "K", "big": "L", "huge": "Cr", "k_div": 1e3, "big_div": 1e5, "huge_div": 1e7},
    "US": {"symbol": "$", "code": "USD", "label": "United States ($)", "k": "K", "big": "K", "huge": "M", "k_div": 1e3, "big_div": 1e3, "huge_div": 1e6},
    "UK": {"symbol": "£", "code": "GBP", "label": "United Kingdom (£)", "k": "K", "big": "K", "huge": "M", "k_div": 1e3, "big_div": 1e3, "huge_div": 1e6},
    "CA": {"symbol": "C$", "code": "CAD", "label": "Canada (C$)", "k": "K", "big": "K", "huge": "M", "k_div": 1e3, "big_div": 1e3, "huge_div": 1e6},
    "AU": {"symbol": "A$", "code": "AUD", "label": "Australia (A$)", "k": "K", "big": "K", "huge": "M", "k_div": 1e3, "big_div": 1e3, "huge_div": 1e6},
}

def detect_currency(df):
    raw = " ".join(df["TRANSACTION DETAILS"].astype(str).str.upper().tolist())
    amt_text = " ".join(df[["WITHDRAWAL AMT", "DEPOSIT AMT", "BALANCE AMT"]].astype(str).values.flatten())
    combined = raw + " " + amt_text
    scores = {"IN": 0, "US": 0, "UK": 0, "CA": 0, "AU": 0}
    
    if re.search(r"CHASE|WELLS\s*FARGO|BANK\s*OF\s*AMERICA|CITI\s*BANK|CAPITAL\s*ONE|US\s*BANK|ZELLE|VENMO|CASHAPP", raw): scores["US"] += 5
    if re.search(r"(?<![CA])\$\d", combined): scores["US"] += 3
    if re.search(r"BARCLAYS|HSBC|NATWEST|LLOYDS|SANTANDER\s*UK|MONZO|REVOLUT|STARLING|FASTER\s*PAYMENT", raw): scores["UK"] += 5
    if "£" in combined: scores["UK"] += 4
    if re.search(r"TD\s*CANADA|SCOTIABANK|CIBC|BMO|RBC\s*ROYAL|TANGERINE|INTERAC|E-?TRANSFER", raw): scores["CA"] += 5
    if re.search(r"C\$\d|CAD", combined): scores["CA"] += 3
    if re.search(r"COMMBANK|COMMONWEALTH\s*BANK|WESTPAC|ANZ\s*BANK|NAB\s*BANK|NAB\b|AFTERPAY|BPAY|OSKO", raw): scores["AU"] += 5
    if re.search(r"A\$\d|AUD", combined): scores["AU"] += 3
    if re.search(r"HDFC|ICICI|SBI|AXIS|KOTAK|IDFC|UPI|NEFT|RTGS|IMPS|@YBL|@OKI?CICI|@PAYTM", raw): scores["IN"] += 5
    if "₹" in combined or "Rs" in combined: scores["IN"] += 4
    
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "IN"

def categorize(desc):
    d = str(desc).upper()

    # ── INCOME & TRANSFERS ──────────────────────────────────────────
    if any(k in d for k in ["SALARY", "SAL ", "PAYROLL", "GIBL", "DIRECT DEP", "DIRECT DEPOSIT",
        "EMPLOYER", "WAGES", "WAGE PAYMENT", "PAYCHEX", "ADP ", "GUSTO"]): return "Salary"
    elif any(k in d for k in ["TRF FROM", "TRANSFER IN", "IMPS/CR", "NEFT/CR", "CREDIT INTEREST",
        "INCOMING WIRE", "INWARD REMITTANCE", "MONEY RECEIVED"]): return "Transfer In"
    elif any(k in d for k in ["TRF TO", "TRANSFER OUT", "FUND TRANSFE", "OUTWARD REMITTANCE",
        "WIRE TRANSFER", "OUTGOING WIRE"]): return "Transfer Out"

    # ── DIGITAL PAYMENTS ────────────────────────────────────────────
    elif "UPI" in d: return "UPI Payment"
    elif any(k in d for k in ["NEFT", "RTGS", "IMPS"]): return "Online Payment"
    elif any(k in d for k in ["POS ", "POS/", "POINT OF SALE", "CARD SWIPE", "ECOM",
        "CONTACTLESS", "DEBIT CARD", "MPS/"]): return "Card Payment"

    # ── CASH ────────────────────────────────────────────────────────
    elif any(k in d for k in ["CASHDEP", "CASH DEP", "CASH DEPOSIT"]): return "Cash Deposit"
    elif any(k in d for k in ["ATM", "CDM", "CASHWDL", "CASH WDL", "CASH WITHDRAWAL",
        "ATM WITHDRAWAL", "CASH MACHINE"]): return "ATM/Cash Withdrawal"

    # ── CHEQUE ──────────────────────────────────────────────────────
    elif any(k in d for k in ["CHQ", "CHEQUE", "CHECK", "CLG"]): return "Cheque"

    # ── CREDIT CARD BILLS ───────────────────────────────────────────
    elif any(k in d for k in ["CREDIT CARD", "CC BILL", "CC PAYMENT", "CARD BILL",
        "CRED ", "CRED/", "CARDPAY", "AMEX PAYMENT", "VISA PAYMENT",
        "MASTERCARD PAYMENT"]): return "Credit Card Bill"

    # ── LOANS & EMI ─────────────────────────────────────────────────
    elif any(k in d for k in ["EMI", "LOAN", "MORTGAGE", "REPAYMENT", "HOME LOAN",
        "CAR LOAN", "STUDENT LOAN", "PERSONAL LOAN", "AUTO LOAN",
        "QUICKEN LOANS", "ROCKET MORTGAGE"]): return "Loan/EMI"

    # ── TAX & GOVERNMENT ────────────────────────────────────────────
    elif any(k in d for k in ["TAX", "GST", "GOVT", "TDS", "INCOME TAX", "MCA", "EPFO", "PF",
        "IRS ", "HMRC", "CRA ", "ATO ", "STATE TAX", "COUNCIL TAX",
        "PROPERTY TAX", "VAT ", "CUSTOMS", "DVLA"]): return "Tax/Government"

    # ── HEALTH & FITNESS (before Entertainment to avoid GYM mismatch) ──
    elif any(k in d for k in ["GYM", "CULT FIT", "CULTFIT", "GYMPASS", "CROSSFIT",
        "YOGA", "FITNESS", "HEALTHIFY", "CURE FIT", "CUREFIT", "PLANET FITNESS",
        "ANYTIME FITNESS", "GOLD'S GYM", "EQUINOX", "PUREGYM", "F45",
        "ORANGETHEORY", "SNAP FITNESS", "CRUNCH FITNESS", "LA FITNESS",
        "24 HOUR FITNESS", "BARRY", "SOULCYCLE"]): return "Health & Fitness"

    # ── GROCERY ─────────────────────────────────────────────────────
    elif any(k in d for k in [
        # India
        "BIGBASKET", "BLINKIT", "ZEPTO", "JIOMART", "DMART", "GROFERS",
        "NATURE BASKET", "SUPR DAILY", "MILKBASKET",
        # US
        "WALMART", "TARGET", "COSTCO", "WHOLE FOODS", "TRADER JOE", "KROGER",
        "SAFEWAY", "PUBLIX", "ALDI", "DOLLAR TREE", "DOLLAR GENERAL",
        "FOOD LION", "WEGMANS", "MEIJER", "HEB ", "SPROUTS", "SMART FINAL",
        "STOP AND SHOP", "GIANT FOOD", "WINCO", "WINN DIXIE", "PIGGLY",
        "MARKET BASKET", "HARRIS TEETER", "FRESH MARKET", "INGLES",
        # UK
        "TESCO", "SAINSBURY", "ASDA", "WAITROSE", "MORRISONS",
        "MARKS SPENCER", "LIDL", "ICELAND", "OCADO", "ALDI UK",
        "CO-OP", "BUDGENS", "SPAR UK",
        # Canada
        "LOBLAWS", "SOBEYS", "METRO INC", "FOOD BASICS", "FRESHCO",
        "NO FRILLS", "REAL CANADIAN", "SAVE ON FOODS", "SUPERSTORE",
        # Australia
        "WOOLWORTHS", "COLES", "IGA ", "ALDI AU", "FOODLAND",
        "HARRIS FARM", "DRAKES", "RITCHIES"]): return "Grocery"

    # ── FOOD & DINING ───────────────────────────────────────────────
    elif any(k in d for k in [
        # India
        "SWIGGY", "ZOMATO", "DOMINOS", "MCDONALD", "KFC", "PIZZA",
        "STARBUCKS", "BURGER", "RESTAURANT", "FOOD", "CAFE", "DINING",
        "DUNZO", "EATSURE", "FAASOS", "HALDIRAM", "BARBEQUE", "CHAAYOS",
        "WOW MOMO", "BOX8", "FRESHMENU",
        # US
        "CHICK-FIL", "CHIPOTLE", "DUNKIN", "SUBWAY", "TACO BELL",
        "WENDYS", "PANERA", "SHAKE SHACK", "FIVE GUYS", "IN-N-OUT",
        "POPEYES", "PANDA EXPRESS", "JACK IN THE BOX", "SONIC DRIVE",
        "DAIRY QUEEN", "APPLEBEES", "OLIVE GARDEN", "CHILIS", "IHOP",
        "DENNY", "WAFFLE HOUSE", "CRACKER BARREL", "RED LOBSTER",
        "OUTBACK", "CHEESECAKE FACTORY", "GRUBHUB", "DOORDASH", "UBER EATS",
        "INSTACART",
        # UK
        "GREGGS", "PRET A MANGER", "NANDOS", "WAGAMAMA", "LEON ",
        "COSTA COFFEE", "CAFFE NERO", "EAT ", "ITSU", "DISHOOM",
        "DELIVEROO", "JUST EAT",
        # Canada
        "TIM HORTONS", "HARVEY", "SWISS CHALET", "BOSTON PIZZA",
        "EAST SIDE MARIO", "SKIP THE DISHES",
        # Australia
        "HUNGRY JACKS", "RED ROOSTER", "NANDOS AU", "GRILL'D",
        "MENULOG", "UBER EATS AU"]): return "Food & Dining"

    # ── TRAVEL & TRANSPORT ──────────────────────────────────────────
    elif any(k in d for k in [
        # India
        "UBER", "OLA", "RAPIDO", "IRCTC", "MAKEMYTRIP", "GOIBIBO",
        "CLEARTRIP", "REDBUS", "YATRA", "FLIGHT", "AIRLINE", "INDIGO",
        "SPICEJET", "RAILWAY", "METRO", "PETROL", "FUEL", "BPCL",
        "HPCL", "IOCL", "FASTAG", "PARKING", "TOLL", "VISTARA",
        "AIR INDIA", "GO FIRST", "AKASA",
        # US
        "DELTA", "UNITED AIRLINES", "AMERICAN AIRLINES", "SOUTHWEST",
        "JETBLUE", "SPIRIT AIR", "FRONTIER AIR", "ALASKA AIR",
        "AMTRAK", "GREYHOUND", "LYFT", "WAYMO", "HERTZ", "AVIS",
        "ENTERPRISE RENT", "BUDGET CAR", "NATIONAL CAR", "DOLLAR CAR",
        "SUNPASS", "EZPASS", "PIKEPASS",
        # UK
        "BRITISH AIRWAYS", "EASYJET", "RYANAIR", "VIRGIN ATLANTIC",
        "NATIONAL RAIL", "TFL ", "OYSTER", "TRAINLINE", "MEGABUS",
        "NATIONAL EXPRESS", "BP ", "SHELL ", "ESSO ",
        # Canada
        "AIR CANADA", "WESTJET", "PORTER AIRLINES", "SUNWING",
        "VIA RAIL", "GO TRANSIT", "PRESTO CARD", "TRANSLINK",
        # Australia
        "QANTAS", "VIRGIN AUSTRALIA", "JETSTAR", "REX AIRLINES",
        "OPAL CARD", "MYKI ", "TRANSPERTH", "GOCARD",
        "7 ELEVEN AU", "BP AU", "CALTEX"]): return "Travel & Transport"

    # ── SHOPPING ────────────────────────────────────────────────────
    elif any(k in d for k in [
        # India
        "AMAZON", "FLIPKART", "MYNTRA", "AJIO", "MEESHO", "SNAPDEAL",
        "RELIANCE RETAIL", "TATA CLIQ", "NYKAA", "CROMA", "VIJAY SALES",
        "WESTSIDE", "TRENT", "PANTALOONS", "LIFESTYLE", "SHOPPERS STOP",
        "DECATHLON", "IKEA", "RELIANCE DIGITAL", "LENSKART",
        "FIRSTCRY", "BEWAKOOF", "URBANIC", "H&M", "ZARA",
        # US
        "BEST BUY", "HOME DEPOT", "LOWES", "MACYS", "NORDSTROM",
        "BLOOMINGDALE", "NEIMAN MARCUS", "SAKS FIFTH", "GAP ", "OLD NAVY",
        "BANANA REPUBLIC", "J CREW", "ANTHROPOLOGIE", "FREE PEOPLE",
        "VICTORIA SECRET", "BATH BODY", "BED BATH", "POTTERY BARN",
        "WILLIAMS SONOMA", "CRATE BARREL", "WAYFAIR", "ETSY", "EBAY",
        "SHOPIFY", "CHEWY", "PETCO", "PETSMART", "AUTOZONE", "OREILLY AUTO",
        "ADVANCE AUTO", "APPLE STORE", "MICROSOFT STORE", "GAMESTOP",
        "BARNES NOBLE", "FIVE BELOW",
        # UK
        "JOHN LEWIS", "NEXT ", "PRIMARK", "RIVER ISLAND", "TOPSHOP",
        "ASOS", "BOOHOO", "PRETTY LITTLE THING", "ARGOS", "CURRYS",
        "PC WORLD", "SCREWFIX", "B&Q", "WICKES", "HOBBYCRAFT",
        # Canada
        "CANADIAN TIRE", "SPORT CHEK", "WINNERS", "HOMESENSE",
        "SIMONS", "REITMANS", "ROOTS ", "INDIGO BOOKS", "BEST BUY CA",
        # Australia
        "BUNNINGS", "KMART AU", "BIG W", "TARGET AU", "JB HI-FI",
        "HARVEY NORMAN", "THE GOOD GUYS", "MYER", "DAVID JONES",
        "REBEL SPORT", "SUPERCHEAP AUTO", "OFFICEWORKS"]): return "Shopping"

    # ── BILLS & UTILITIES ───────────────────────────────────────────
    elif any(k in d for k in [
        # India
        "ELECTRIC", "ELECTRICITY", "WATER BILL", "GAS BILL", "BESCOM",
        "TATA POWER", "ADANI", "BROADBAND", "INTERNET", "WIFI",
        "ACT FIBERNET", "AIRTEL", "JIO", "VODAFONE", "VI ", "BSNL",
        "MOBILE RECHARGE", "RECHARGE", "DTH", "TATA SKY", "DISH TV",
        "POSTPAID", "PREPAID",
        # US
        "AT&T", "VERIZON", "T-MOBILE", "SPRINT", "COMCAST", "XFINITY",
        "COX COMMUNICATIONS", "SPECTRUM", "DIRECTV", "DISH NETWORK",
        "FRONTIER COMM", "CONSOLIDATED COMM", "DOMINION ENERGY",
        "DUKE ENERGY", "GEORGIA POWER", "PACIFIC GAS", "CON EDISON",
        "NATIONAL GRID", "PEOPLES GAS", "NICOR GAS",
        # UK
        "BRITISH GAS", "E.ON", "EDF ENERGY", "SCOTTISH POWER",
        "OCTOPUS ENERGY", "OVO ENERGY", "BULB ENERGY", "SOUTHERN WATER",
        "THAMES WATER", "SKY UK", "BT GROUP", "VIRGIN MEDIA", "TALKTALK",
        "O2 UK", "THREE UK", "EE LIMITED",
        # Canada
        "ROGERS", "BELL CANADA", "TELUS", "SHAW", "VIDEOTRON",
        "HYDRO ONE", "BC HYDRO", "ENMAX", "FORTISBC",
        # Australia
        "AGL ENERGY", "ORIGIN ENERGY", "ENERGY AUSTRALIA",
        "TELSTRA", "OPTUS", "VODAFONE AU", "TPG TELECOM",
        "IINET", "AUSSIE BROADBAND", "FOXTEL"]): return "Bills & Utilities"

    # ── INSURANCE ───────────────────────────────────────────────────
    elif any(k in d for k in [
        # India
        "INSURANCE", "LIC ", "HDFC LIFE", "ICICI PRUDENTIAL", "SBI LIFE",
        "POLICY", "PREMIUM", "HEALTH INSURANCE", "STAR HEALTH",
        "MAX LIFE", "BAJAJ ALLIANZ",
        # US
        "GEICO", "STATE FARM", "PROGRESSIVE INS", "ALLSTATE", "USAA",
        "NATIONWIDE INS", "TRAVELERS INS", "LIBERTY MUTUAL",
        "FARMERS INS", "AETNA", "CIGNA", "HUMANA", "BLUE CROSS",
        "UNITED HEALTH",
        # UK
        "AVIVA", "AXA UK", "BUPA ", "ADMIRAL INS", "DIRECT LINE",
        "HASTINGS DIRECT", "COMPARE THE MARKET",
        # Canada
        "SUNLIFE", "MANULIFE", "GREAT WEST LIFE", "INTACT INSURANCE",
        "TD INSURANCE",
        # Australia
        "MEDIBANK", "BUPA AU", "HCF HEALTH", "NIB HEALTH",
        "NRMA INSURANCE", "RACQ", "SUNCORP"]): return "Insurance"

    # ── ENTERTAINMENT ───────────────────────────────────────────────
    elif any(k in d for k in [
        "NETFLIX", "HOTSTAR", "PRIME VIDEO", "SPOTIFY", "YOUTUBE",
        "DISNEY", "SONY LIV", "ZEE5", "APPLE", "GOOGLE PLAY",
        "SUBSCRIPTION", "MEMBERSHIP", "AUDIBLE", "BOOKMYSHOW",
        "BOOK MY SHOW", "PVR", "INOX", "CINEPOLIS", "MOVIE", "CINEMA",
        "HBO ", "HULU", "PEACOCK", "PARAMOUNT", "DISCOVERY PLUS",
        "APPLE TV", "AMAZON PRIME", "CRUNCHYROLL", "FUNIMATION",
        "TWITCH", "PLAYSTATION", "XBOX", "NINTENDO", "STEAM ",
        "EPIC GAMES", "EA GAMES", "UBISOFT", "ACTIVISION",
        "AMC THEATRE", "REGAL CINEMA", "ODEON", "VUE CINEMA",
        "IMAX", "EVENT CINEMAS", "HOYTS",
        "TICKETMASTER", "STUBHUB", "SEATGEEK", "LIVENATION"]): return "Entertainment"

    # ── EDUCATION ───────────────────────────────────────────────────
    elif any(k in d for k in [
        "SCHOOL", "COLLEGE", "UNIVERSITY", "TUITION", "COURSE",
        "UDEMY", "COURSERA", "UNACADEMY", "BYJU", "EDUCATION",
        "EXAM FEE", "UPGRAD", "KHAN ACADEMY", "SKILLSHARE",
        "LINKEDIN LEARNING", "PLURALSIGHT", "CODECADEMY",
        "DUOLINGO", "MASTERCLASS", "BRILLIANT ORG",
        "CHEGG", "GRAMMARLY", "QUIZLET"]): return "Education"

    # ── RENT & HOUSING ──────────────────────────────────────────────
    elif any(k in d for k in ["HOUSE RENT", "PG RENT", "MAINTENANCE", "SOCIETY",
        "AIRBNB", "VRBO", "BOOKING.COM ACCOMMODATION"]) or \
         ((" RENT" in d or d.startswith("RENT") or "/RENT" in d) and "TRENT" not in d): return "Rent & Housing"

    # ── MEDICAL & HEALTH ────────────────────────────────────────────
    elif any(k in d for k in [
        # India
        "HOSPITAL", "PHARMACY", "MEDICAL", "DOCTOR", "CLINIC",
        "APOLLO", "MEDPLUS", "1MG", "PHARMEASY", "NETMEDS",
        "DIAGNOSTIC", "PATHLAB", "DENTAL",
        # US
        "CVS PHARMACY", "WALGREENS", "RITE AID", "DUANE READE",
        "KAISER", "MAYO CLINIC", "CLEVELAND CLINIC",
        "LABCORP", "QUEST DIAGNOSTICS", "URGENT CARE",
        # UK
        "BOOTS PHARMACY", "SUPERDRUG", "LLOYDS PHARMACY",
        "NHS ", "SPECSAVERS", "VISION EXPRESS",
        # Canada
        "SHOPPERS DRUG", "REXALL", "LONDON DRUGS", "JEAN COUTU",
        # Australia
        "CHEMIST WAREHOUSE", "PRICELINE PHARMACY",
        "TERRY WHITE", "NATIONAL PHARMACIES"]): return "Medical & Health"

    # ── INVESTMENTS ─────────────────────────────────────────────────
    elif any(k in d for k in [
        # India
        "MUTUAL FUND", "SIP ", "ZERODHA", "GROWW", "KUVERA",
        "DEMAT", "NSE ", "BSE ", "COIN ", "IPO",
        "SMALLCASE", "PPF", "NPS ", "FD ", "FIXED DEPOSIT", "RD ",
        # US/Global
        "FIDELITY", "VANGUARD", "SCHWAB", "TD AMERITRADE",
        "ETRADE", "ROBINHOOD", "WEBULL", "COINBASE", "BINANCE",
        "KRAKEN", "WEALTHSIMPLE", "BETTERMENT", "STASH INVEST",
        # UK
        "HARGREAVES LANSDOWN", "AJ BELL", "NUTMEG",
        "FREETRADE", "TRADING 212"]): return "Investments"

    # ── BANK CHARGES ────────────────────────────────────────────────
    elif any(k in d for k in ["SERVICE CHARGE", "BANK CHARGE", "ANNUAL FEE", "LATE FEE",
        "PENALTY", "INTEREST CHARGED", "DEBIT INTEREST", "MIN BAL",
        "OVERDRAFT FEE", "NSF FEE", "MONTHLY FEE",
        "MAINTENANCE FEE", "WIRE FEE", "FOREIGN TXN FEE"]): return "Bank Charges"

    # ── DIGITAL WALLETS ─────────────────────────────────────────────
    elif any(k in d for k in [
        # India
        "PHONEPE", "PAYTM", "GPAY", "GOOGLE PAY", "MOBIKWIK",
        "FREECHARGE", "WALLET", "LAZYPAY", "SIMPL", "SLICE", "BHARATPE",
        # Global
        "VENMO", "ZELLE", "CASHAPP", "CASH APP", "PAYPAL",
        "APPLE PAY", "GOOGLE WALLET", "SAMSUNG PAY",
        # UK/EU
        "MONZO", "REVOLUT", "STARLING", "WISE ", "CURVE ",
        # Canada
        "INTERAC E-TRANSFER",
        # Australia
        "BEEM IT", "OSKO"]): return "Digital Wallet"

    # ── BILL PAYMENT GATEWAYS ────────────────────────────────────────
    elif any(k in d for k in ["BILLDESK", "RAZORPAY", "PAYU", "CASHFREE", "CCAVENUE",
        "PAYGATE", "PAYMENT GATEWAY", "INSTAMOJO",
        "STRIPE", "SQUARE ", "BRAINTREE", "ADYEN"]): return "Bill Payment"

    # ── AUTO DEBIT ──────────────────────────────────────────────────
    elif any(k in d for k in ["SI/", "ECS/", "ECS ", "NACH/", "NACH ", "AUTO DEBIT",
        "STANDING INSTRUCTION", "MANDATE", "E-MANDATE", "AUTOPAY",
        "RECURRING", "AUTO-PAY", "SCHEDULED PAYMENT"]): return "Auto-Debit"

    # ── REFUNDS ─────────────────────────────────────────────────────
    elif any(k in d for k in ["REFUND", "REVERSAL", "CASHBACK", "REVERSL", "REV/",
        "FAILED TXN", "RETURN", "CHARGEBACK",
        "CREDIT ADJUSTMENT", "GOODWILL CREDIT"]): return "Refund"

    # ── DIVIDEND & INTEREST ─────────────────────────────────────────
    elif any(k in d for k in ["DIVIDEND", "DIV/", "INT ON", "INTEREST CREDIT",
        "INT.CREDIT", "BONUS", "CAPITAL GAINS", "DISTRIBUTION"]): return "Dividend/Interest"

    # ── INTERNATIONAL ───────────────────────────────────────────────
    elif any(k in d for k in ["SWIFT", "FOREX", "WIRE TRANSFER", "FOREIGN",
        "INTERNATIONAL", "CROSS BORDER", "FCY", "REMITTANCE",
        "WESTERN UNION", "MONEYGRAM", "TRANSFERWISE", "WORLDREMIT"]): return "International"

    # ── FOOD DELIVERY SPECIFIC ──────────────────────────────────────
    elif any(k in d for k in ["GRUBHUB", "DOORDASH", "UBER EATS", "INSTACART",
        "DELIVEROO", "JUST EAT", "SKIP THE DISHES",
        "MENULOG", "FOODORA"]): return "Food & Dining"

    # ── BANK MISC ───────────────────────────────────────────────────
    elif any(k in d for k in ["DEBIT MEMO", "ADJUSTMENT", "CLEARING", "SETTLEMENT",
        "SUSPENSE", "CONSOLIDATED", "MISC"]): return "Bank Misc"

    else: return "Other"
