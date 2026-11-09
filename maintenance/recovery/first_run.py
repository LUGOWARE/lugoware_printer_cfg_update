"""Inline touch-friendly setup; no motion, heating or reset commands."""
import ipaddress
import logging
import subprocess
import threading
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib, Pango
from ks_includes.screen_panel import ScreenPanel
from ks_includes import first_run_state as state

TEXT = {'ar': ['الإعداد الأولي',
        'اختيار اللغة',
        'الشبكة',
        'المنطقة الزمنية',
        'التالي',
        'السابق',
        'تخطي',
        'إنهاء الإعداد',
        'تُطبّق اللغة المختارة فورًا.',
        'يمكنك المتابعة دون اتصال.',
        'اختر منطقة زمنية لحفظها فورًا.',
        'جارٍ الحفظ…',
        'تم الحفظ',
        'تعذّر الحفظ. يرجى المحاولة مجددًا.',
        'لم تكتمل إعادة ضبط المصنع. شغّل أداة إعادة الضبط مجددًا.',
        'متصل',
        'غير متصل'],
 'bg': ['Първоначална настройка',
        'Език',
        'Мрежа',
        'Часова зона',
        'Напред',
        'Назад',
        'Пропускане',
        'Завършване',
        'Избраният език се прилага веднага.',
        'Можете да продължите без връзка.',
        'Изберете часова зона, за да я запазите веднага.',
        'Запазване…',
        'Запазено',
        'Неуспешно запазване. Опитайте отново.',
        'Фабричното нулиране не е завършено. Стартирайте инструмента отново.',
        'Свързано',
        'Няма връзка'],
 'cs': ['Úvodní nastavení',
        'Jazyk',
        'Síť',
        'Časové pásmo',
        'Další',
        'Zpět',
        'Přeskočit',
        'Dokončit nastavení',
        'Vybraný jazyk se použije okamžitě.',
        'Můžete pokračovat bez připojení.',
        'Výběrem se časové pásmo ihned uloží.',
        'Ukládání…',
        'Uloženo',
        'Uložení se nezdařilo. Zkuste to znovu.',
        'Obnovení výrobního nastavení není dokončeno. Spusťte nástroj znovu.',
        'Připojeno',
        'Nepřipojeno'],
 'da': ['Første opsætning',
        'Sprog',
        'Netværk',
        'Tidszone',
        'Næste',
        'Tilbage',
        'Spring over',
        'Afslut opsætning',
        'Det valgte sprog anvendes med det samme.',
        'Du kan fortsætte uden forbindelse.',
        'Vælg en tidszone for at gemme den med det samme.',
        'Gemmer…',
        'Gemt',
        'Kunne ikke gemme. Prøv igen.',
        'Fabriksnulstillingen er ikke fuldført. Kør værktøjet igen.',
        'Forbundet',
        'Ikke forbundet'],
 'de': ['Ersteinrichtung',
        'Sprache',
        'Netzwerk',
        'Zeitzone',
        'Weiter',
        'Zurück',
        'Überspringen',
        'Einrichtung abschließen',
        'Die ausgewählte Sprache wird sofort übernommen.',
        'Sie können ohne Verbindung fortfahren.',
        'Die ausgewählte Zeitzone wird sofort gespeichert.',
        'Wird gespeichert…',
        'Gespeichert',
        'Speichern fehlgeschlagen. Bitte erneut versuchen.',
        'Die Werkseinstellung wurde nicht vollständig wiederhergestellt. Starten Sie das Werkzeug erneut.',
        'Verbunden',
        'Nicht verbunden'],
 'de_formal': ['Ersteinrichtung',
               'Sprache',
               'Netzwerk',
               'Zeitzone',
               'Weiter',
               'Zurück',
               'Überspringen',
               'Einrichtung abschließen',
               'Die ausgewählte Sprache wird sofort übernommen.',
               'Sie können ohne Verbindung fortfahren.',
               'Die ausgewählte Zeitzone wird sofort gespeichert.',
               'Wird gespeichert…',
               'Gespeichert',
               'Speichern fehlgeschlagen. Bitte erneut versuchen.',
               'Die Werkseinstellung wurde nicht vollständig wiederhergestellt. Starten Sie das Werkzeug '
               'erneut.',
               'Verbunden',
               'Nicht verbunden'],
 'en': ['Welcome',
        'Language',
        'Network',
        'Time zone',
        'Next',
        'Back',
        'Skip',
        'Finish setup',
        'The selected language applies immediately.',
        'You can continue without a connection.',
        'Select a time zone to save it immediately.',
        'Saving…',
        'Saved',
        'Unable to save. Please try again.',
        'Factory reset is incomplete. Run the factory tool again.',
        'Connected',
        'Not connected'],
 'es': ['Configuración inicial',
        'Idioma',
        'Red',
        'Zona horaria',
        'Siguiente',
        'Atrás',
        'Omitir',
        'Finalizar',
        'El idioma seleccionado se aplica inmediatamente.',
        'Puede continuar sin conexión.',
        'Seleccione una zona horaria para guardarla inmediatamente.',
        'Guardando…',
        'Guardado',
        'No se pudo guardar. Inténtelo de nuevo.',
        'El restablecimiento de fábrica no se ha completado. Ejecute la herramienta de nuevo.',
        'Conectado',
        'Sin conexión'],
 'et': ['Esmane seadistamine',
        'Keel',
        'Võrk',
        'Ajavöönd',
        'Edasi',
        'Tagasi',
        'Jäta vahele',
        'Lõpeta seadistamine',
        'Valitud keel rakendub kohe.',
        'Võite jätkata ilma ühenduseta.',
        'Valitud ajavöönd salvestatakse kohe.',
        'Salvestamine…',
        'Salvestatud',
        'Salvestamine ebaõnnestus. Proovige uuesti.',
        'Tehaseseadete taastamine pole lõpetatud. Käivitage tööriist uuesti.',
        'Ühendatud',
        'Ühendamata'],
 'fa': ['راه\u200cاندازی اولیه',
        'انتخاب زبان',
        'شبکه',
        'منطقه زمانی',
        'بعدی',
        'قبلی',
        'رد شدن',
        'پایان راه\u200cاندازی',
        'زبان انتخاب\u200cشده فوراً اعمال می\u200cشود.',
        'می\u200cتوانید بدون اتصال ادامه دهید.',
        'با انتخاب منطقه زمانی، فوراً ذخیره می\u200cشود.',
        'در حال ذخیره…',
        'ذخیره شد',
        'ذخیره نشد. دوباره تلاش کنید.',
        'بازنشانی کارخانه کامل نشده است. ابزار بازنشانی را دوباره اجرا کنید.',
        'متصل',
        'قطع اتصال'],
 'fr': ['Configuration initiale',
        'Langue',
        'Réseau',
        'Fuseau horaire',
        'Suivant',
        'Précédent',
        'Ignorer',
        'Terminer',
        'La langue sélectionnée est appliquée immédiatement.',
        'Vous pouvez continuer sans connexion.',
        'Le fuseau horaire sélectionné est enregistré immédiatement.',
        'Enregistrement…',
        'Enregistré',
        'Échec de l’enregistrement. Veuillez réessayer.',
        'La réinitialisation d’usine est incomplète. Relancez l’outil.',
        'Connecté',
        'Non connecté'],
 'he': ['הגדרה ראשונית',
        'שפה',
        'רשת',
        'אזור זמן',
        'הבא',
        'הקודם',
        'דילוג',
        'סיום ההגדרה',
        'השפה שנבחרה מוחלת מיד.',
        'אפשר להמשיך ללא חיבור.',
        'אזור הזמן שנבחר נשמר מיד.',
        'שומר…',
        'נשמר',
        'השמירה נכשלה. נסו שוב.',
        'האיפוס להגדרות היצרן לא הושלם. הפעילו שוב את כלי האיפוס.',
        'מחובר',
        'לא מחובר'],
 'hr': ['Početno postavljanje',
        'Jezik',
        'Mreža',
        'Vremenska zona',
        'Dalje',
        'Natrag',
        'Preskoči',
        'Završi postavljanje',
        'Odabrani jezik primjenjuje se odmah.',
        'Možete nastaviti bez veze.',
        'Odabrana vremenska zona odmah se sprema.',
        'Spremanje…',
        'Spremljeno',
        'Spremanje nije uspjelo. Pokušajte ponovno.',
        'Vraćanje na tvorničke postavke nije dovršeno. Ponovno pokrenite alat.',
        'Povezano',
        'Nije povezano'],
 'hu': ['Kezdeti beállítás',
        'Nyelv',
        'Hálózat',
        'Időzóna',
        'Tovább',
        'Vissza',
        'Kihagyás',
        'Beállítás befejezése',
        'A kiválasztott nyelv azonnal érvénybe lép.',
        'Kapcsolat nélkül is folytathatja.',
        'A kiválasztott időzóna azonnal mentésre kerül.',
        'Mentés…',
        'Mentve',
        'Nem sikerült menteni. Próbálja újra.',
        'A gyári visszaállítás nem fejeződött be. Futtassa újra az eszközt.',
        'Csatlakoztatva',
        'Nincs kapcsolat'],
 'it': ['Configurazione iniziale',
        'Lingua',
        'Rete',
        'Fuso orario',
        'Avanti',
        'Indietro',
        'Salta',
        'Completa configurazione',
        'La lingua selezionata viene applicata subito.',
        'Puoi continuare senza connessione.',
        'Il fuso orario selezionato viene salvato subito.',
        'Salvataggio…',
        'Salvato',
        'Salvataggio non riuscito. Riprova.',
        'Il ripristino di fabbrica non è completo. Esegui di nuovo lo strumento.',
        'Connesso',
        'Non connesso'],
 'jp': ['初期設定',
        '言語選択',
        'ネットワーク',
        'タイムゾーン',
        '次へ',
        '戻る',
        'スキップ',
        '設定を完了',
        '選択した言語はすぐに適用されます。',
        '接続せずに進むこともできます。',
        'タイムゾーンを選択するとすぐに保存されます。',
        '保存中…',
        '保存しました',
        '保存できませんでした。もう一度お試しください。',
        '工場出荷状態への初期化が完了していません。初期化ツールを再実行してください。',
        '接続済み',
        '未接続'],
 'ko': ['처음 설정',
        '언어 선택',
        '네트워크 연결',
        '시간대 설정',
        '다음',
        '이전',
        '건너뛰기',
        '설정 완료',
        '선택 즉시 언어가 적용됩니다.',
        '연결 없이도 진행할 수 있습니다.',
        '시간대를 선택하면 바로 저장됩니다.',
        '저장 중…',
        '저장됨',
        '저장하지 못했습니다. 다시 선택해 주세요.',
        '출고 초기화가 완료되지 않았습니다. 초기화 프로그램으로 다시 진행해 주세요.',
        '연결됨',
        '연결되지 않음'],
 'lt': ['Pradinis nustatymas',
        'Kalba',
        'Tinklas',
        'Laiko juosta',
        'Toliau',
        'Atgal',
        'Praleisti',
        'Baigti nustatymą',
        'Pasirinkta kalba pritaikoma iš karto.',
        'Galite tęsti be ryšio.',
        'Pasirinkta laiko juosta išsaugoma iš karto.',
        'Išsaugoma…',
        'Išsaugota',
        'Nepavyko išsaugoti. Bandykite dar kartą.',
        'Gamyklinių nustatymų atkūrimas nebaigtas. Paleiskite įrankį dar kartą.',
        'Prisijungta',
        'Neprisijungta'],
 'nl': ['Eerste installatie',
        'Taal',
        'Netwerk',
        'Tijdzone',
        'Volgende',
        'Terug',
        'Overslaan',
        'Installatie voltooien',
        'De geselecteerde taal wordt direct toegepast.',
        'U kunt zonder verbinding doorgaan.',
        'De geselecteerde tijdzone wordt direct opgeslagen.',
        'Opslaan…',
        'Opgeslagen',
        'Opslaan mislukt. Probeer het opnieuw.',
        'De fabrieksreset is niet voltooid. Voer het hulpprogramma opnieuw uit.',
        'Verbonden',
        'Niet verbonden'],
 'pl': ['Pierwsza konfiguracja',
        'Język',
        'Sieć',
        'Strefa czasowa',
        'Dalej',
        'Wstecz',
        'Pomiń',
        'Zakończ konfigurację',
        'Wybrany język zostanie zastosowany natychmiast.',
        'Możesz kontynuować bez połączenia.',
        'Wybrana strefa czasowa zostanie od razu zapisana.',
        'Zapisywanie…',
        'Zapisano',
        'Nie udało się zapisać. Spróbuj ponownie.',
        'Przywracanie ustawień fabrycznych nie zostało ukończone. Uruchom narzędzie ponownie.',
        'Połączono',
        'Brak połączenia'],
 'pt': ['Configuração inicial',
        'Idioma',
        'Rede',
        'Fuso horário',
        'Seguinte',
        'Voltar',
        'Ignorar',
        'Concluir configuração',
        'O idioma selecionado é aplicado imediatamente.',
        'Pode continuar sem ligação.',
        'O fuso horário selecionado é guardado imediatamente.',
        'A guardar…',
        'Guardado',
        'Não foi possível guardar. Tente novamente.',
        'A reposição de fábrica não foi concluída. Execute novamente a ferramenta.',
        'Ligado',
        'Sem ligação'],
 'pt_BR': ['Configuração inicial',
           'Idioma',
           'Rede',
           'Fuso horário',
           'Próximo',
           'Voltar',
           'Pular',
           'Concluir configuração',
           'O idioma selecionado é aplicado imediatamente.',
           'Você pode continuar sem conexão.',
           'O fuso horário selecionado é salvo imediatamente.',
           'Salvando…',
           'Salvo',
           'Não foi possível salvar. Tente novamente.',
           'A restauração de fábrica não foi concluída. Execute a ferramenta novamente.',
           'Conectado',
           'Desconectado'],
 'rs': ['Почетно подешавање',
        'Језик',
        'Мрежа',
        'Временска зона',
        'Даље',
        'Назад',
        'Прескочи',
        'Заврши подешавање',
        'Изабрани језик се одмах примењује.',
        'Можете наставити без везе.',
        'Изабрана временска зона се одмах чува.',
        'Чување…',
        'Сачувано',
        'Чување није успело. Покушајте поново.',
        'Враћање на фабричка подешавања није завршено. Поново покрените алатку.',
        'Повезано',
        'Није повезано'],
 'ru': ['Первоначальная настройка',
        'Язык',
        'Сеть',
        'Часовой пояс',
        'Далее',
        'Назад',
        'Пропустить',
        'Завершить настройку',
        'Выбранный язык применяется сразу.',
        'Можно продолжить без подключения.',
        'Выбранный часовой пояс сохраняется сразу.',
        'Сохранение…',
        'Сохранено',
        'Не удалось сохранить. Повторите попытку.',
        'Сброс к заводским настройкам не завершён. Запустите инструмент повторно.',
        'Подключено',
        'Не подключено'],
 'sk': ['Úvodné nastavenie',
        'Jazyk',
        'Sieť',
        'Časové pásmo',
        'Ďalej',
        'Späť',
        'Preskočiť',
        'Dokončiť nastavenie',
        'Vybraný jazyk sa použije okamžite.',
        'Môžete pokračovať bez pripojenia.',
        'Vybrané časové pásmo sa ihneď uloží.',
        'Ukladanie…',
        'Uložené',
        'Uloženie zlyhalo. Skúste to znova.',
        'Obnovenie výrobných nastavení nie je dokončené. Spustite nástroj znova.',
        'Pripojené',
        'Nepripojené'],
 'sl': ['Začetna nastavitev',
        'Jezik',
        'Omrežje',
        'Časovni pas',
        'Naprej',
        'Nazaj',
        'Preskoči',
        'Končaj nastavitev',
        'Izbrani jezik se uporabi takoj.',
        'Nadaljujete lahko brez povezave.',
        'Izbrani časovni pas se takoj shrani.',
        'Shranjevanje…',
        'Shranjeno',
        'Shranjevanje ni uspelo. Poskusite znova.',
        'Ponastavitev na tovarniške nastavitve ni dokončana. Znova zaženite orodje.',
        'Povezano',
        'Ni povezave'],
 'sv': ['Första konfigurationen',
        'Språk',
        'Nätverk',
        'Tidszon',
        'Nästa',
        'Tillbaka',
        'Hoppa över',
        'Slutför konfiguration',
        'Det valda språket används direkt.',
        'Du kan fortsätta utan anslutning.',
        'Den valda tidszonen sparas direkt.',
        'Sparar…',
        'Sparat',
        'Det gick inte att spara. Försök igen.',
        'Fabriksåterställningen är inte klar. Kör verktyget igen.',
        'Ansluten',
        'Inte ansluten'],
 'tr': ['İlk kurulum',
        'Dil',
        'Ağ',
        'Saat dilimi',
        'İleri',
        'Geri',
        'Atla',
        'Kurulumu tamamla',
        'Seçilen dil hemen uygulanır.',
        'Bağlantı olmadan devam edebilirsiniz.',
        'Seçilen saat dilimi hemen kaydedilir.',
        'Kaydediliyor…',
        'Kaydedildi',
        'Kaydedilemedi. Lütfen tekrar deneyin.',
        'Fabrika ayarlarına sıfırlama tamamlanmadı. Aracı tekrar çalıştırın.',
        'Bağlı',
        'Bağlı değil'],
 'uk': ['Початкове налаштування',
        'Мова',
        'Мережа',
        'Часовий пояс',
        'Далі',
        'Назад',
        'Пропустити',
        'Завершити налаштування',
        'Вибрана мова застосовується одразу.',
        'Можна продовжити без підключення.',
        'Вибраний часовий пояс зберігається одразу.',
        'Збереження…',
        'Збережено',
        'Не вдалося зберегти. Спробуйте ще раз.',
        'Скидання до заводських налаштувань не завершено. Запустіть засіб повторно.',
        'Підключено',
        'Не підключено'],
 'vi': ['Thiết lập ban đầu',
        'Ngôn ngữ',
        'Mạng',
        'Múi giờ',
        'Tiếp theo',
        'Quay lại',
        'Bỏ qua',
        'Hoàn tất',
        'Ngôn ngữ đã chọn được áp dụng ngay.',
        'Bạn có thể tiếp tục khi không có kết nối.',
        'Múi giờ đã chọn được lưu ngay.',
        'Đang lưu…',
        'Đã lưu',
        'Không thể lưu. Vui lòng thử lại.',
        'Chưa hoàn tất khôi phục cài đặt gốc. Hãy chạy lại công cụ.',
        'Đã kết nối',
        'Chưa kết nối'],
 'zh': ['首次设置',
        '选择语言',
        '网络连接',
        '时区设置',
        '下一步',
        '上一步',
        '跳过',
        '完成设置',
        '选择语言后立即生效。',
        '您也可以离线继续。',
        '选择时区后立即保存。',
        '正在保存…',
        '已保存',
        '无法保存，请重试。',
        '出厂重置未完成，请重新运行初始化工具。',
        '已连接',
        '未连接'],
 'zh_CN': ['首次设置',
           '选择语言',
           '网络连接',
           '时区设置',
           '下一步',
           '上一步',
           '跳过',
           '完成设置',
           '选择语言后立即生效。',
           '您也可以离线继续。',
           '选择时区后立即保存。',
           '正在保存…',
           '已保存',
           '无法保存，请重试。',
           '出厂重置未完成，请重新运行初始化工具。',
           '已连接',
           '未连接'],
 'zh_TW': ['首次設定',
           '選擇語言',
           '網路連線',
           '時區設定',
           '下一步',
           '上一步',
           '略過',
           '完成設定',
           '選擇語言後立即套用。',
           '也可以離線繼續。',
           '選擇時區後立即儲存。',
           '儲存中…',
           '已儲存',
           '無法儲存，請重試。',
           '尚未完成出廠重設，請重新執行重設工具。',
           '已連線',
           '未連線']}

TIMEZONE_PROMPTS={
 'ko':('나라를 선택하세요.','도시·시간대를 선택하세요.'),
 'en':('Select a country.','Select a city / time zone.'),
 'ar':('اختر دولة.','اختر مدينة / منطقة زمنية.'),
 'bg':('Изберете държава.','Изберете град / часова зона.'),
 'cs':('Vyberte zemi.','Vyberte město / časové pásmo.'),
 'da':('Vælg et land.','Vælg en by / tidszone.'),
 'de':('Wählen Sie ein Land.','Wählen Sie eine Stadt / Zeitzone.'),
 'es':('Seleccione un país.','Seleccione una ciudad / zona horaria.'),
 'et':('Valige riik.','Valige linn / ajavöönd.'),
 'fa':('کشور را انتخاب کنید.','شهر / منطقه زمانی را انتخاب کنید.'),
 'fr':('Sélectionnez un pays.','Sélectionnez une ville / un fuseau horaire.'),
 'he':('בחרו מדינה.','בחרו עיר / אזור זמן.'),
 'hr':('Odaberite državu.','Odaberite grad / vremensku zonu.'),
 'hu':('Válasszon országot.','Válasszon várost / időzónát.'),
 'it':('Seleziona un paese.','Seleziona una città / un fuso orario.'),
 'jp':('国を選択してください。','都市・タイムゾーンを選択してください。'),
 'lt':('Pasirinkite šalį.','Pasirinkite miestą / laiko juostą.'),
 'nl':('Selecteer een land.','Selecteer een stad / tijdzone.'),
 'pl':('Wybierz kraj.','Wybierz miasto / strefę czasową.'),
 'pt':('Selecione um país.','Selecione uma cidade / fuso horário.'),
 'rs':('Изаберите државу.','Изаберите град / временску зону.'),
 'ru':('Выберите страну.','Выберите город / часовой пояс.'),
 'sk':('Vyberte krajinu.','Vyberte mesto / časové pásmo.'),
 'sl':('Izberite državo.','Izberite mesto / časovni pas.'),
 'sv':('Välj ett land.','Välj en stad / tidszon.'),
 'tr':('Bir ülke seçin.','Bir şehir / saat dilimi seçin.'),
 'uk':('Виберіть країну.','Виберіть місто / часовий пояс.'),
 'vi':('Chọn quốc gia.','Chọn thành phố / múi giờ.'),
 'zh':('请选择国家。','请选择城市／时区。'),
 'zh_tw':('請選擇國家。','請選擇城市／時區。'),
}

def connected_address(address):
    try:
        ip=ipaddress.ip_address(str(address).split('/')[0])
        return not (ip.is_loopback or ip.is_unspecified or ip.is_link_local)
    except ValueError:return False

class Panel(ScreenPanel):
    def __init__(self,screen,title):
        super().__init__(screen,title)
        self.step=min(2,max(0,int(state.read().get('step',0))))
        self.child=None;self.poll=None;self.busy=False;self.active=True
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,hexpand=True,vexpand=True)
        self.box.set_border_width(12)
        self.box.get_style_context().add_class('factory-wizard')
        language=self._config.get_main_config().get('language','en').split('_')[0]
        if language in ('ar','fa','he'):self.box.set_direction(Gtk.TextDirection.RTL)
        css=Gtk.CssProvider();css.load_from_data(b'''
        .factory-wizard button {background-image:none;background-color:#252525;border:0;
          border-radius:4px;box-shadow:none;padding:10px;}
        .factory-wizard button:active,.factory-wizard button.selected {background-color:#424242;}
        .factory-wizard .wizard-choice label {font-size:22px;font-weight:400;
          font-style:normal;font-family:"Noto Sans","Noto Sans CJK KR",sans-serif;}
        .factory-wizard .wizard-caption {font-size:16px;color:#bdbdbd;}
        .factory-wizard .wizard-heading {font-size:22px;font-weight:bold;}
        .factory-wizard .wizard-page {font-size:18px;font-weight:400;color:#bdbdbd;}
        .factory-wizard scrollbar {min-width:14px;opacity:1;background-color:#1a1a1a;}
        .factory-wizard scrollbar slider {min-width:10px;min-height:44px;
          background-color:#777777;border:2px solid #1a1a1a;border-radius:5px;}
        ''')
        Gtk.StyleContext.add_provider_for_screen(self.content.get_screen(),css,Gtk.STYLE_PROVIDER_PRIORITY_USER+10)
        self.content.add(self.box);self.draw()

    def tr(self):
        lang=self._config.get_main_config().get('language','en').replace('-','_').lower()
        lang={'ja':'jp','sr':'rs','zh_hant':'zh_tw','zh_hans':'zh_cn'}.get(lang,lang)
        catalogs={key.lower():value for key,value in TEXT.items()}
        return catalogs.get(lang,catalogs.get(lang.split('_')[0],TEXT['en']))

    def button(self,text,callback,choice=False):
        b=Gtk.Button()
        b.add(Gtk.Label(label=text,xalign=0 if choice else .5,wrap=True,
                        wrap_mode=Pango.WrapMode.WORD_CHAR,max_width_chars=24 if choice else 16))
        b.set_size_request(-1,76 if choice else 58)
        if choice:b.get_style_context().add_class('wizard-choice')
        b.connect('clicked',callback);return b

    def stop_child(self):
        if self.poll:
            if GLib.MainContext.default().find_source_by_id(self.poll):GLib.source_remove(self.poll)
            self.poll=None
        if self.child:
            self.child.deactivate()
            source=getattr(self.child,'conn_status',None)
            if source and GLib.MainContext.default().find_source_by_id(source):GLib.source_remove(source)
            self._screen.remove_keyboard()

    def draw(self):
        self.stop_child();self.child=None
        for c in self.box.get_children():c.destroy()
        t=self.tr()
        header=Gtk.Box(spacing=12,hexpand=True)
        header.set_direction(Gtk.TextDirection.LTR)
        heading=Gtk.Label(label=t[self.step+1],xalign=0,hexpand=True,
                          wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,max_width_chars=22)
        self.heading=heading
        heading.get_style_context().add_class('wizard-heading')
        self.page_label=Gtk.Label(label=f'{self.step+1} / 3',xalign=1,halign=Gtk.Align.END)
        self.page_label.set_direction(Gtk.TextDirection.LTR)
        self.page_label.get_style_context().add_class('wizard-page')
        header.pack_start(heading,True,True,0)
        header.pack_end(self.page_label,False,False,0)
        self.box.pack_start(header,False,False,4)
        if state.read().get('status') in ('resetting','failed'):
            self.box.pack_start(Gtk.Label(label=t[14],wrap=True,justify=Gtk.Justification.CENTER),True,True,0)
            self.box.show_all();return
        self.caption=Gtk.Label(label=t[8+self.step],wrap=True,justify=Gtk.Justification.CENTER)
        self.caption.get_style_context().add_class('wizard-caption')
        self.caption.set_no_show_all(True)
        if self.step!=0:self.box.pack_start(self.caption,False,False,0)
        self.center=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,hexpand=True,vexpand=True)
        self.box.pack_start(self.center,True,True,0)
        nav=Gtk.Box(spacing=12,homogeneous=True)
        if self.step:nav.pack_start(self.button(t[5],lambda w:self.previous()),True,True,0)
        self.next_button=self.button(t[7] if self.step==2 else t[6] if self.step==1 else t[4],lambda w:self.advance(1))
        nav.pack_start(self.next_button,True,True,0);self.box.pack_end(nav,False,False,0)
        if self.step==0:self.languages()
        elif self.step==1:self.network()
        else:self.timezones()
        self.box.show_all()

    def listing(self):
        scroll=Gtk.ScrolledWindow(hexpand=True,vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False);scroll.set_kinetic_scrolling(True)
        rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        scroll.add(rows);self.center.pack_start(scroll,True,True,0)
        self.choice_scroll=scroll
        return rows

    def languages(self):
        from ks_includes.lugo_language_names import language_name
        rows=self.listing();selected=self._config.get_main_config().get('language','en')
        self.language_buttons={}
        for code in self._config.lang_list:
            b=self.button(language_name(code),lambda w,c=code:self.language(w,c),True)
            # Keep native language names in a consistent font family, size and
            # weight regardless of the currently selected interface language.
            family={'ko':'Noto Sans CJK KR','jp':'Noto Sans CJK JP',
                    'zh_CN':'Noto Sans CJK SC','zh_TW':'Noto Sans CJK TC',
                    'ar':'Noto Sans Arabic','fa':'Noto Sans Arabic',
                    'he':'Noto Sans Hebrew'}.get(code,'Noto Sans')
            attrs=Pango.AttrList()
            attrs.insert(Pango.attr_family_new(family))
            attrs.insert(Pango.attr_size_new_absolute(22*Pango.SCALE))
            attrs.insert(Pango.attr_weight_new(Pango.Weight.NORMAL))
            attrs.insert(Pango.attr_style_new(Pango.Style.NORMAL))
            b.get_child().set_attributes(attrs)
            if code==selected:b.get_style_context().add_class('selected')
            self.language_buttons[code]=b
            rows.pack_start(b,False,False,0)
        self.language_scroll=self.choice_scroll
        self.language_restore=getattr(self._screen,'_first_run_language_scroll',None)
        self.language_scroll.connect('size-allocate',lambda *args:GLib.idle_add(self.restore_language_scroll))

    def restore_language_scroll(self):
        if self.language_restore is None or not self.active:return False
        adjustment=self.language_scroll.get_vadjustment()
        if adjustment.get_page_size()<=0:return False
        maximum=max(adjustment.get_lower(),adjustment.get_upper()-adjustment.get_page_size())
        adjustment.set_value(min(maximum,max(adjustment.get_lower(),self.language_restore)))
        self.language_restore=None
        return False

    def language(self,widget,code):
        if code==self._config.get_main_config().get('language','en'):return
        self._screen._first_run_language_scroll=self.language_scroll.get_vadjustment().get_value()
        # Install translations without reload_panels(): keep the same widgets,
        # allocations, focus and scroll adjustment throughout the tap.
        self._config.install_language(code)
        self._screen.env.install_gettext_translations(self._config.get_lang())
        self._config._create_configurable_options(self._screen)
        self._config.set('main','language',code)
        self._config.save_user_config_options()
        # Other cached screens pick up their new translations when opened.
        self._screen.panels_reinit=[name for name,panel in self._screen.panels.items() if panel is not self]
        for name,button in self.language_buttons.items():
            context=button.get_style_context()
            context.add_class('selected') if name==code else context.remove_class('selected')
        t=self.tr()
        self.heading.set_text(t[1])
        self.next_button.get_child().set_text(t[4])

    def network(self):
        try:
            from panels.network import Panel as NetworkPanel
            self.child=NetworkPanel(self._screen,self.tr()[2])
            self.child.content.set_size_request(-1,-1)
            self.center.pack_start(self.child.content,True,True,0)
            if hasattr(self.child,'scroll'):
                # Bypass the regular menu's scrollbar-hiding subclass only here.
                Gtk.ScrolledWindow.set_policy(self.child.scroll,Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
                self.child.scroll.set_overlay_scrolling(False)
            # Show Wi-Fi choices even when Ethernet is already connected.
            devices=getattr(self.child,'network_devices',[])
            wifi=next((d['interface'] for d in devices if d.get('type')==2),None)
            selector=getattr(self.child,'labels',{}).get('interface')
            if wifi and wifi!=self.child.interface and hasattr(selector,'set_active_id'):
                selector.set_active_id(wifi)
            self.child.activate();self.network_status()
            self.poll=GLib.timeout_add_seconds(2,self.network_status)
        except Exception:
            logging.exception('First-run network panel unavailable')
            self.caption.set_text(self.tr()[16]+' · '+self.tr()[9])
            self.caption.show()

    def network_status(self):
        if self.step!=1 or not self.active:return False
        connected=False
        try:
            nm=self.child.sdbus_nm
            connected=bool(nm and any(connected_address(nm.get_ip_for_interface(i)) for i in nm.get_interfaces()))
        except Exception:logging.debug('Network status unavailable',exc_info=True)
        t=self.tr();self.next_button.get_child().set_text(t[4] if connected else t[6])
        self.caption.set_text('' if connected else t[16]+' · '+t[9])
        self.caption.set_visible(not connected)
        return True

    def timezones(self):
        from panels.timezone import zones,current_zone,translations
        self.zone_catalog,_=translations(self._config.get_main_config())
        self.selected_zone=current_zone();self.countries=zones()
        self.selected_country=next((c for c,z in self.countries.items() if self.selected_zone in z),None)
        self.show_countries()

    def clear_choices(self):
        for child in self.center.get_children():child.destroy()

    def timezone_prompt(self,index):
        lang=self._config.get_main_config().get('language','en').replace('-','_').lower()
        lang={'ja':'jp','sr':'rs','zh_hant':'zh_tw'}.get(lang,lang)
        return TIMEZONE_PROMPTS.get(lang,TIMEZONE_PROMPTS.get(lang.split('_')[0],TIMEZONE_PROMPTS['en']))[index]

    def show_countries(self):
        if self.busy:return
        self.tz_page='countries';self.clear_choices()
        self.next_button.set_sensitive(True)
        self.caption.set_text(self.timezone_prompt(0));self.caption.show()
        rows=self.listing();names=self.zone_catalog['countries']
        for country in sorted(self.countries,key=lambda c:(c!=self.selected_country,names.get(c,c))):
            b=self.button(names.get(country,country),lambda w,c=country:self.show_regions(c),True)
            if country==self.selected_country:b.get_style_context().add_class('selected')
            rows.pack_start(b,False,False,0)
        self.center.show_all()

    def show_regions(self,country):
        if self.busy:return
        self.tz_page='regions';self.clear_choices()
        self.next_button.set_sensitive(country==self.selected_country)
        catalog=self.zone_catalog
        self.caption.set_text(self.timezone_prompt(1))
        self.caption.show()
        rows=self.listing();self.zone_buttons={}
        for zone in self.countries[country]:
            label=catalog['cities'].get(zone,zone.rsplit('/',1)[-1].replace('_',' '))
            b=self.button(label,lambda w,z=zone:self.set_zone(z),True)
            if zone==self.selected_zone:b.get_style_context().add_class('selected')
            self.zone_buttons[zone]=b;rows.pack_start(b,False,False,0)
        self.center.show_all()

    def set_zone(self,zone):
        if self.busy:return
        self.busy=True;self.next_button.set_sensitive(False);self.caption.set_text(self.tr()[11])
        self.caption.show()
        def work():
            try:
                subprocess.run(['/usr/bin/timedatectl','--no-ask-password','set-timezone',zone],check=True,capture_output=True,timeout=20)
                from panels.timezone import current_zone
                ok=current_zone()==zone
            except (OSError,subprocess.SubprocessError):ok=False
            GLib.idle_add(self.zone_saved,zone,ok)
        threading.Thread(target=work,daemon=True).start()

    def zone_saved(self,zone,ok):
        self.busy=False
        if not self.active or self.step!=2:return False
        self.next_button.set_sensitive(ok);self.caption.set_text(self.tr()[12]+' · '+zone if ok else self.tr()[13])
        if ok:
            self.selected_zone=zone
            self.selected_country=next((c for c,z in self.countries.items() if zone in z),None)
            for key,b in self.zone_buttons.items():
                c=b.get_style_context();c.add_class('selected') if key==zone else c.remove_class('selected')
        return False

    def advance(self,direction):
        if self.busy:return
        self.stop_child();self.step+=direction
        if self.step>2:
            state.save({'status':'complete','step':2});self._screen.state_ready(wait=False);return
        state.save({'status':'pending','step':self.step});self.draw()

    def back(self):
        if self.busy:return True
        if self.child and self.child.back():return True
        if self.step:self.previous()
        return True

    def previous(self):
        if self.busy:return
        if self.step==2 and getattr(self,'tz_page',None)=='regions':self.show_countries()
        else:self.advance(-1)

    def activate(self):self.active=True
    def deactivate(self):self.active=False;self.stop_child()
