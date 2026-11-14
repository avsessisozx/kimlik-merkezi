; Kimlik Merkezi kurulum paketi. Kullanıcı bazlı: yönetici izni GEREKMEZ.
; Derleme: ISCC /DSurum=0.1.1 /DKaynak=<PyInstaller dist\KimlikMerkezi> KimlikMerkezi.iss
#ifndef Surum
  #define Surum "0.1.1"
#endif
#define AppAd "Kimlik Merkezi"

[Setup]
AppId={{B7C31E44-5D0A-4E7B-9B0C-4D2F6E1A9C20}
AppName={#AppAd}
AppVersion={#Surum}
AppPublisher=Kimlik Merkezi
PrivilegesRequired=lowest
DefaultDirName={autopf}\KimlikMerkezi
DisableProgramGroupPage=yes
OutputDir=cikti
OutputBaseFilename=KimlikMerkezi-{#Surum}-kurulum
SetupIconFile=app.ico
UninstallDisplayIcon={app}\KimlikMerkezi.exe
UninstallDisplayName={#AppAd}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: otobaslat; Description: "Windows açılışında otomatik başlat (tepside; sonra Ayarlar'dan kapatılabilir)"

[Files]
Source: "{#Kaynak}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\{#AppAd}"; Filename: "{app}\KimlikMerkezi.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KimlikMerkezi"; ValueData: """{app}\KimlikMerkezi.exe"" --arka-plan"; Tasks: otobaslat; Flags: uninsdeletevalue

[Run]
Filename: "{app}\KimlikMerkezi.exe"; Description: "{#AppAd} uygulamasını şimdi aç"; Flags: nowait postinstall skipifsilent
; Uygulama içi güncelleme (guncelleme.py) kurulumu sessiz başlatır ve /GUNCELLEME=1 verir: 'postinstall' girdisi sessizde
; çalışmaz, bu yüzden uygulama burada yeniden açılır. Normal (elle) sessiz kurulumda /GUNCELLEME yoktur: açılmaz.
Filename: "{app}\KimlikMerkezi.exe"; Flags: nowait skipifdoesntexist; Check: GuncellemedenGeldi

[Code]
function GuncellemedenGeldi(): Boolean;
begin
  Result := (ExpandConstant('{param:GUNCELLEME|0}') = '1');
end;

procedure UygulamayiKapat();
var
  kod: Integer;
begin
  { Çalışan kopya dosyaları kilitlemesin. Hata önemsenmez. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM KimlikMerkezi.exe', '', SW_HIDE, ewWaitUntilTerminated, kod);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM kimlikmerkezi-mcp.exe', '', SW_HIDE, ewWaitUntilTerminated, kod);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  UygulamayiKapat();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  UygulamayiKapat();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  veri, ayar: String;
  sil: Boolean;
begin
  if CurUninstallStep <> usPostUninstall then Exit;
  if not RegQueryStringValue(HKCU, 'Software\KimlikMerkezi', 'VeriKlasoru', veri) then Exit;
  { Güvenlik: yalnızca gerçekten bir Kimlik Merkezi veri klasörüyse (kimlik.db var) silinir. }
  if not FileExists(veri + '\kimlik.db') then Exit;
  if UninstallSilent() then
    { Sessiz kaldırmada VARSAYILAN: veriyi silme. Açıkça /SILVERIYI=1 verilirse siler. }
    sil := (ExpandConstant('{param:SILVERIYI|0}') = '1')
  else
    { Soruda varsayılan düğme "Hayır" (veriyi silme). }
    sil := (MsgBox('Kimlik Merkezi programı kaldırıldı.' + #13#10#13#10 +
             'Kişisel verileriniz şu klasörde duruyor:' + #13#10 + veri + #13#10#13#10 +
             'Bu verileri de KALICI olarak silmek istiyor musunuz? (Geri alınamaz)',
             mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES);
  if sil then
  begin
    DelTree(veri, True, True, True);
    ayar := ExpandConstant('{localappdata}\KimlikMerkezi');
    DelTree(ayar, True, True, True);
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\KimlikMerkezi');
  end;
end;
