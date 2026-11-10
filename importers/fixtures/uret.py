import json, os, sys
from pathlib import Path
root = Path(sys.argv[1])

def w(p, text):
    p = root / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

def wj(p, obj):
    w(p, json.dumps(obj, ensure_ascii=False, indent=1))

YT = "https://www.youtube.com"
def watch(vid, title, ch, t, deleted=False):
    r = {"header": "YouTube", "title": title, "titleUrl": f"{YT}/watch?v={vid}", "time": t,
         "products": ["YouTube"], "activityControls": ["YouTube watch history"]}
    if ch:
        r["subtitles"] = [{"name": ch, "url": f"{YT}/channel/UC{ch[:1]*22}"}]
    return r

W1 = watch("aaaaaaaaaaa", "Watched Ornek Video Bir", "Kanal A", "2024-03-01T10:00:00.123Z")
W2 = watch("bbbbbbbbbbb", "Watched Ornek Video Iki", "Kanal B", "2024-03-02T11:00:00Z")
W3 = {"header": "YouTube", "title": f"Watched {YT}/watch?v=ccccccccccc", "titleUrl": f"{YT}/watch?v=ccccccccccc",
      "time": "2024-03-03T12:00:00Z", "products": ["YouTube"], "activityControls": ["YouTube watch history"]}
W4 = {"header": "YouTube", "title": "Viewed Ornek topluluk gonderisi", "titleUrl": f"{YT}/post/Ugkxornek",
      "time": "2024-03-04T13:00:00Z", "products": ["YouTube"], "activityControls": ["YouTube watch history"]}
SR = lambda q, t: {"header": "YouTube", "title": f"Searched for {q}", "titleUrl": f"{YT}/results?search_query={q.replace(' ', '+')}",
                   "time": t, "products": ["YouTube"], "activityControls": ["YouTube search history"]}
SEARCH_YT = [SR("ornek arama bir", "2024-03-05T09:00:00Z"), SR("ornek arama iki", "2024-03-06T09:30:00Z")]
SUBS = ("Channel ID,Channel URL,Channel title\n"
        "UCaaaaaaaaaaaaaaaaaaaaaa,http://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa,Kanal A\n"
        "UCbbbbbbbbbbbbbbbbbbbbbb,http://www.youtube.com/channel/UCbbbbbbbbbbbbbbbbbbbbbb,Kanal B\n"
        "UCcccccccccccccccccccccc,http://www.youtube.com/channel/UCcccccccccccccccccccccc,\"Kanal, virgullu\"\n")
GS1 = {"header": "Search", "title": "Searched for ornek google arama", "titleUrl": "https://www.google.com/search?q=ornek+google+arama",
       "time": "2024-04-01T08:00:00Z", "products": ["Search"], "activityControls": ["Web & App Activity"]}
GS2 = {"header": "Search", "title": "Searched for ornek yer", "titleUrl": "https://www.google.com/search?q=ornek+yer",
       "time": "2024-04-02T08:00:00Z", "products": ["Search"],
       "locationInfos": [{"name": "Ornek konum", "url": "https://www.google.com/maps/@41.123456,29.123456,15z?entry=s",
                          "source": "From your device", "sourceUrl": "https://support.google.com/"}]}
GS3 = {"header": "Search", "title": "Zamansiz kayit", "titleUrl": "https://www.google.com/search?q=zamansiz"}
CH = {"Browser History": [
    {"favicon_url": "https://example.test/f.ico", "page_transition": "LINK", "title": "Ornek Sayfa Bir",
     "url": "https://example.test/bir", "client_id": "cid1", "time_usec": 1709287200000000},
    {"page_transition": "TYPED", "title": "Ornek Sayfa Iki", "url": "https://example.test/iki",
     "client_id": "cid1", "time_usec": 1709290800000000},
    {"page_transition": "LINK", "title": "Ornek Sayfa Uc", "url": "https://example.test/uc?x=1",
     "client_id": "cid1", "time_usec": 1709294400000000},
    {"page_transition": "LINK", "title": "Ornek Harita", "url": "https://www.google.com/maps/place/Ornek/@40.987654,28.987654,17z",
     "client_id": "cid1", "time_usec": 1709298000000000}]}
MBOX = (
    "From 1000000000000000001@xxx Mon Mar 04 10:00:00 +0000 2024\n"
    "X-GM-THRID: 1000000000000000001\nX-Gmail-Labels: Inbox,Important,Category Updates\n"
    "Date: Mon, 4 Mar 2024 10:00:00 +0000\nFrom: Ornek Gonderen <gonderen@example.test>\n"
    "To: ben@example.test\nSubject: =?UTF-8?Q?=C3=96rnek_konu_=C5=9F=C4=B1k?=\n"
    "Message-ID: <msg-1@example.test>\nMIME-Version: 1.0\n"
    "Content-Type: text/plain; charset=UTF-8\nContent-Transfer-Encoding: quoted-printable\n\n"
    "Merhaba, bu =C3=B6rnek bir metindir. Anahtar: epostaozelkelime.\n"
    ">From satiri gövdede kacislanmis.\n\n"
    "From 1000000000000000002@xxx Tue Mar 05 11:00:00 +0000 2024\n"
    "X-Gmail-Labels: Sent\nDate: Tue, 5 Mar 2024 14:00:00 +0300\nFrom: ben@example.test\n"
    "To: baska@example.test\nSubject: HTML ileti\nMessage-ID: <msg-2@example.test>\n"
    "MIME-Version: 1.0\nContent-Type: multipart/alternative; boundary=\"b1\"\n\n"
    "--b1\nContent-Type: text/html; charset=UTF-8\n\n"
    "<html><style>x{}</style><body><p>HTML <b>govde</b> metni</p></body></html>\n--b1--\n\n"
    "From 1000000000000000003@xxx Wed Mar 06 12:00:00 +0000 2024\n"
    "X-Gmail-Labels: Inbox\nDate: Wed, 6 Mar 2024 12:00:00 +0000\nFrom: fatura@example.test\n"
    "To: ben@example.test\nSubject: Ekli ileti\nMessage-ID: <msg-3@example.test>\n"
    "MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=\"b2\"\n\n"
    "--b2\nContent-Type: text/plain; charset=UTF-8\n\nEk var.\n--b2\n"
    "Content-Type: application/pdf; name=\"ornek.pdf\"\nContent-Disposition: attachment; filename=\"ornek.pdf\"\n"
    "Content-Transfer-Encoding: base64\n\nU0VOVEVUSUtfRUtfSUNFUklLX0VLU0lLX0RFR0lM\n--b2--\n\n"
    "From 1000000000000000004@xxx Thu Mar 07 13:00:00 +0000 2024\n"
    "X-Gmail-Labels: Spam\nFrom: tarihsiz@example.test\nTo: ben@example.test\n"
    "Subject: Date basligi yok\nMessage-ID: <msg-4@example.test>\n\nGovde.\n"
)

def build(base, names):
    n = names
    wj(f"{base}/{n['yt']}/{n['hist']}/{n['watch']}", [W1, W2, W3, W4])
    wj(f"{base}/{n['yt']}/{n['hist']}/{n['search']}", SEARCH_YT)
    w(f"{base}/{n['yt']}/{n['subs']}/{n['subsf']}", n['subshdr'] + SUBS.split("\n", 1)[1])
    wj(f"{base}/{n['act']}/{n['ytact']}/{n['actf']}", [W1, watch("ddddddddddd", "Watched Ornek Video Dort", "Kanal D", "2024-03-07T14:00:00Z")])
    wj(f"{base}/{n['act']}/{n['srch']}/{n['actf']}", [GS1, GS2, GS3])
    wj(f"{base}/{n['chrome']}/{n['chromef']}", CH)
    w(f"{base}/{n['mail']}/{n['mbox']}", MBOX)
    w(f"{base}/archive_browser.html", "<html><body>ozet</body></html>")
    wj(f"{base}/Profile/Profile.json", {"displayName": "Ornek"})

EN = dict(yt="YouTube and YouTube Music", hist="history", watch="watch-history.json", search="search-history.json",
          subs="subscriptions", subsf="subscriptions.csv", subshdr="Channel ID,Channel URL,Channel title\n",
          act="My Activity", ytact="YouTube", srch="Search", actf="MyActivity.json",
          chrome="Chrome", chromef="History.json", mail="Mail", mbox="All mail Including Spam and Trash.mbox")
# Türkçe adlar: VARSAYIM (gerçek bir Türkçe Takeout görülmedi); yalnız içerikle tanımayı sınamak için.
TR = dict(yt="YouTube ve YouTube Music", hist="geçmiş", watch="izleme geçmişi.json", search="arama geçmişi.json",
          subs="abonelikler", subsf="abonelikler.csv", subshdr="Kanal Kimliği,Kanal URL'si,Kanal başlığı\n",
          act="Etkinliklerim", ytact="YouTube", srch="Arama", actf="Etkinliklerim.json",
          chrome="Chrome", chromef="Tarayıcı Geçmişi.json", mail="Posta", mbox="Tüm posta.mbox")
build("takeout_en/Takeout", EN) if False else None
root.mkdir(parents=True, exist_ok=True)
build("takeout_en/Takeout", EN)
build("takeout_tr/Takeout", TR)

# eski ad: BrowserHistory.json
wj("takeout_eski_chrome/Takeout/Chrome/BrowserHistory.json", CH)

# HTML biçimli Takeout (JSON yok)
w("takeout_html/Takeout/My Activity/Search/MyActivity.html",
  '<html><body><div class="mdl-grid"><div class="content-cell">ornek</div></div></body></html>')

# Reddit
D = "2023-01-15 12:34:56 UTC"
w("reddit/comments.csv", "id,permalink,date,ip,subreddit,gildings,link,parent,body,media\n"
  f"c1,/r/ornek/comments/p1/_/c1/,{D},1.2.3.4,ornek,0,/r/ornek/comments/p1/,,\"Ornek yorum bir, virgullu\nikinci satir\",\n"
  f"c2,/r/ornek/comments/p1/_/c2/,2023-01-16 01:02:03 UTC,1.2.3.4,ornek,0,/r/ornek/comments/p1/,c1,Ornek yorum iki,\n"
  f"c3,/r/diger/comments/p2/_/c3/,2023-02-01 10:00:00 UTC,1.2.3.4,diger,0,/r/diger/comments/p2/,,Ornek yorum uc,\n")
w("reddit/posts.csv", "id,permalink,date,ip,subreddit,gildings,title,url,body\n"
  f"p1,/r/ornek/comments/p1/,2023-01-10 08:00:00 UTC,1.2.3.4,ornek,0,Ornek baslik bir,,Ornek govde bir\n"
  f"p2,/r/diger/comments/p2/,2023-01-11 09:00:00 UTC,1.2.3.4,diger,0,Ornek baslik iki,https://example.test/x,\n")
w("reddit/messages.csv", "id,permalink,thread_id,date,ip,from,to,subject,body\n"
  "m1,/message/messages/m1,t1,2023-03-01 10:00:00 UTC,1.2.3.4,ornekkullanici,digerkullanici,Ornek konu,Ozel mesaj govdesi bir\n"
  "m2,/message/messages/m2,t1,2023-03-02 10:00:00 UTC,1.2.3.4,digerkullanici,ornekkullanici,Re: Ornek konu,Ozel mesaj govdesi iki\n")
w("reddit/chat_history.csv", "message_id,created_at,updated_at,username,message,thread_parent_message_id,channel_url,subreddit,channel_name,conversation_type\n"
  "x1,2023-04-01 10:00:00 UTC,,ornekkullanici,Sohbet mesaji bir,,https://chat.example.test/1,,Ornek kanal,\n"
  "x2,2023-04-01 10:05:00 UTC,,digerkullanici,Sohbet mesaji iki,,https://chat.example.test/1,,Ornek kanal,\n")
w("reddit/post_votes.csv", "id,permalink,direction\np1,/r/ornek/comments/p1/,up\np2,/r/diger/comments/p2/,down\n")
w("reddit/saved_posts.csv", "id,permalink\np1,/r/ornek/comments/p1/\np9,/r/baska/comments/p9/\n")
w("reddit/subscribed_subreddits.csv", "subreddit\nornek\ndiger\nbaska\n")
w("reddit/statistics.csv", "statistic,value\naccount_created,2020-01-01\n")
w("reddit/ip_logs.csv", "date,ip\n2023-01-01 00:00:00 UTC,1.2.3.4\n")
w("README.md", "# Fixture'lar\n\nHepsi sentetik, uydurma içerik; gerçek kişisel veri yok.\n"
  "- takeout_en: İngilizce Takeout yapısı (biçim bilgisi için durum/importers.md).\n"
  "- takeout_tr: Türkçe klasör/dosya adları VARSAYIMDIR (gerçek Türkçe Takeout görülmedi); yalnız içerikle tanımayı sınar.\n"
  "- takeout_eski_chrome: eski `BrowserHistory.json` adı. takeout_html: yalnız HTML (desteklenmez).\n"
  "- reddit: hesap veri isteği CSV'leri (sütunlar doğrulanmadı).\n")
