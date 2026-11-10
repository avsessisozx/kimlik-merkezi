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


# ------------------------------------------------------------------ Meta (Instagram / Facebook)
def moji(s):  # Meta'nın bilinen sorunu: UTF-8 baytları latin-1 sanılıp \u00XX kaçışlanır
    return s.encode("utf-8").decode("latin-1")


def wm(p, obj):  # ensure_ascii=True: kaçışlı dosya (Meta gibi)
    p = root / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1), encoding="utf-8")


IG = "meta_instagram/instagram-ornek-2024/"
sld = lambda title, href, value, ts: {"title": title, "media_list_data": [],
                                      "string_list_data": [{"href": href, "value": value, "timestamp": ts}]}
wm(IG + "your_instagram_activity/likes/liked_posts.json", {"likes_media_likes": [
    sld("ornekkullanici1", "https://www.instagram.com/p/AAA111/", "❤", 1700000000),
    sld("ornekkullanici2", "https://www.instagram.com/p/BBB222/", "❤", 1700000100)]})
wm(IG + "your_instagram_activity/likes/liked_comments.json", {"likes_comment_likes": [
    sld("ornekkullanici3", "https://www.instagram.com/p/CCC333/", "❤", 1700000200)]})
wm(IG + "your_instagram_activity/comments/post_comments_1.json", [
    {"string_map_data": {"Comment": {"value": moji("Güzel şık yorum bir")}, "Media Owner": {"value": "ornekkullanici1"},
                         "Time": {"timestamp": 1700001000}}},
    {"string_map_data": {"Comment": {"value": "yorum iki"}, "Media Owner": {"value": "ornekkullanici2"},
                         "Time": {"timestamp": 1700001100}}}])
wm(IG + "your_instagram_activity/content/posts_1.json", [
    {"media": [{"uri": "media/posts/202311/a.jpg", "creation_timestamp": 1700002000,
                "title": moji("Örnek açıklama şık"), "media_metadata": {"photo_metadata": {"exif_data": []}}}]},
    {"media": [{"uri": "media/posts/202311/b.jpg", "creation_timestamp": 1700002100, "title": "konumlu gonderi",
                "media_metadata": {"photo_metadata": {"exif_data": [{"latitude": 41.0123, "longitude": 28.9765}]}}}]}])
wm(IG + "connections/followers_and_following/following.json", {"relationships_following": [
    sld("", "https://www.instagram.com/_u/takip1", "takip1", 1700003000),
    sld("", "https://www.instagram.com/_u/takip2", "takip2", 1700003100),
    sld("", "https://www.instagram.com/_u/takip3", "takip3", 1700003200)]})
wm(IG + "connections/followers_and_following/followers_1.json", [
    sld("", "https://www.instagram.com/_u/takipci1", "takipci1", 1700004000),
    sld("", "https://www.instagram.com/_u/takipci2", "takipci2", 1700004100)])
wm(IG + "your_instagram_activity/messages/inbox/ornekarkadas_123/message_1.json", {
    "participants": [{"name": "ornekarkadas"}, {"name": "ornekkullanici"}],
    "messages": [
        {"sender_name": "ornekarkadas", "timestamp_ms": 1700005000000, "content": moji("Merhaba şık mesaj"), "type": "Generic"},
        {"sender_name": "ornekkullanici", "timestamp_ms": 1700005060000, "content": "Ozel mesaj iki", "type": "Generic",
         "photos": [{"uri": "x.jpg"}]},
        {"sender_name": "ornekarkadas", "timestamp_ms": 1700005120000, "content": "Ozel mesaj uc", "type": "Generic",
         "share": {"link": "https://example.test/p", "share_text": "paylasim"}},
        {"sender_name": "ornekarkadas", "content": "zamansiz mesaj"}],
    "title": "ornekarkadas", "thread_path": "inbox/ornekarkadas_123"})

FBD = "meta_facebook/facebook-ornek-2024/"
wm(FBD + "your_facebook_activity/posts/your_posts__check_ins__photos_and_videos_1.json", [
    {"timestamp": 1700010000, "data": [{"post": moji("Facebook gönderisi bir")}], "title": ""},
    {"timestamp": 1700010100, "data": [{"post": "gonderi iki"}], "title": "yer paylasimi",
     "attachments": [{"data": [{"place": {"name": "Ornek Yer", "coordinate": {"latitude": 40.5, "longitude": 29.5},
                                          "address": "ornek adres"}}]}]}])
wm(FBD + "your_facebook_activity/comments_and_reactions/comments.json", {"comments_v2": [
    {"timestamp": 1700011000, "data": [{"comment": {"timestamp": 1700011000, "comment": moji("Şık yorum"), "author": "Ornek Kisi"}}],
     "title": "Ornek Kisi yorum yapti"},
    {"timestamp": 1700011100, "data": [{"comment": {"timestamp": 1700011100, "comment": "yorum iki", "author": "Ornek Kisi"}}],
     "title": "Ornek Kisi yorum yapti"}]})
wm(FBD + "your_facebook_activity/comments_and_reactions/likes_and_reactions_1.json", {"reactions_v2": [
    {"timestamp": 1700012000, "data": [{"reaction": {"reaction": "LIKE", "actor": "Ornek Kisi"}}], "title": "Ornek Kisi begendi"},
    {"timestamp": 1700012100, "data": [{"reaction": {"reaction": "LOVE", "actor": "Ornek Kisi"}}], "title": "Ornek Kisi sevdi"}]})
wm(FBD + "connections/friends/friends.json", {"friends_v2": [
    {"name": "Ornek Arkadas Bir", "timestamp": 1700013000}, {"name": moji("Ornek Arkadaş İki"), "timestamp": 1700013100}]})
wm(FBD + "your_facebook_activity/messages/inbox/fbarkadas_456/message_1.json", {
    "participants": [{"name": "Ornek Arkadas"}],
    "messages": [{"sender_name": "Ornek Arkadas", "timestamp_ms": 1700014000000, "content": "fb mesaj bir", "type": "Generic"},
                 {"sender_name": "Ornek Kisi", "timestamp_ms": 1700014060000, "content": "fb mesaj iki", "type": "Generic"}],
    "title": "Ornek Arkadas", "thread_path": "inbox/fbarkadas_456"})
w("meta_html/instagram-ornek/your_instagram_activity/likes/liked_posts.html", "<html><body>begeniler</body></html>")


# ------------------------------------------------------------------ GitHub (JSON dosyaları; testte tar.gz yapılır)
GH = "github/"
O = "https://github.com/ornekkullanici"
wj(GH + "repositories_000001.json", [
    {"type": "repository", "url": f"{O}/ornek-depo", "name": "ornek-depo", "description": "Ornek depo aciklamasi",
     "private": False, "language": "Python", "created_at": "2022-01-02T03:04:05Z", "owner": O},
    {"type": "repository", "url": f"{O}/gizli-depo", "name": "gizli-depo", "description": None, "private": True,
     "created_at": "2022-06-07T08:09:10Z", "owner": O}])
wj(GH + "issues_000001.json", [
    {"type": "issue", "url": f"{O}/ornek-depo/issues/1", "repository": f"{O}/ornek-depo", "title": "Ornek issue basligi",
     "body": "Ornek issue govdesi", "state": "open", "created_at": "2022-02-01T10:00:00Z"},
    {"type": "issue", "url": f"{O}/ornek-depo/issues/2", "repository": f"{O}/ornek-depo", "title": "Ikinci issue",
     "body": "govde", "state": "closed", "created_at": "2022-02-02T10:00:00Z"},
    {"type": "issue", "url": f"{O}/ornek-depo/issues/3", "title": "Zamansiz issue"}])
wj(GH + "issue_comments_000001.json", [
    {"type": "issue_comment", "url": f"{O}/ornek-depo/issues/1#issuecomment-1", "body": "Ornek yorum metni",
     "created_at": "2022-02-03T10:00:00Z"},
    {"type": "issue_comment", "url": f"{O}/ornek-depo/issues/1#issuecomment-2", "body": "Ikinci yorum",
     "created_at": "2022-02-04T10:00:00Z"}])
wj(GH + "pull_requests_000001.json", [
    {"type": "pull_request", "url": f"{O}/ornek-depo/pull/5", "title": "Ornek PR", "body": "PR govdesi",
     "state": "merged", "created_at": "2022-03-01T10:00:00Z"}])
wj(GH + "stars_000001.json", [
    {"type": "star", "repository": "https://github.com/baska/yildizli-depo", "created_at": "2022-04-01T10:00:00Z"},
    {"type": "star", "repository": "https://github.com/baska/ikinci-depo", "created_at": "2022-04-02T10:00:00Z"}])
wj(GH + "users_000001.json", [{"type": "user", "login": "ornekkullanici", "emails": ["gizli@example.test"],
                               "created_at": "2020-01-01T00:00:00Z"}])
wj(GH + "public_keys_000001.json", [{"type": "public_key", "title": "laptop", "key": "ssh-rsa AAAAORNEK",
                                     "created_at": "2021-01-01T00:00:00Z"}])
wj(GH + "schema.json", {"version": "1.2.3", "ornek": True})
