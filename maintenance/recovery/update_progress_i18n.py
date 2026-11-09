"""Translations for the update progress UI; diagnostic logs remain verbatim."""
KEYS = ('running', 'complete', 'failed', 'details', 'notice')
ROWS = {
 'en': ('Updating…','Update complete','Update failed','View update details','The firmware may restart during the update.'),
 'ko': ('업데이트 중…','업데이트 완료','업데이트 실패','업데이트 내역 확인','업데이트 중 펌웨어가 재부팅 될 수 있습니다.'),
 'zh_CN': ('正在更新…','更新完成','更新失败','查看更新详情','更新期间固件可能会重启。'),
 'zh_TW': ('正在更新…','更新完成','更新失敗','查看更新詳情','更新期間韌體可能會重新啟動。'),
 'jp': ('更新中…','更新完了','更新に失敗しました','更新の詳細を確認','更新中にファームウェアが再起動する場合があります。'),
 'ar': ('جارٍ التحديث…','اكتمل التحديث','فشل التحديث','عرض تفاصيل التحديث','قد تتم إعادة تشغيل البرنامج الثابت أثناء التحديث.'),
 'bg': ('Обновяване…','Обновяването завърши','Неуспешно обновяване','Подробности за обновяването','Фърмуерът може да се рестартира по време на обновяването.'),
 'cs': ('Probíhá aktualizace…','Aktualizace dokončena','Aktualizace selhala','Zobrazit podrobnosti aktualizace','Během aktualizace se může firmware restartovat.'),
 'da': ('Opdaterer…','Opdatering fuldført','Opdatering mislykkedes','Vis opdateringsdetaljer','Firmwaren kan genstarte under opdateringen.'),
 'de': ('Aktualisierung läuft…','Aktualisierung abgeschlossen','Aktualisierung fehlgeschlagen','Aktualisierungsdetails anzeigen','Die Firmware kann während der Aktualisierung neu starten.'),
 'es': ('Actualizando…','Actualización completada','Error de actualización','Ver detalles de la actualización','El firmware puede reiniciarse durante la actualización.'),
 'et': ('Uuendamine…','Uuendamine lõpetatud','Uuendamine ebaõnnestus','Vaata uuenduse üksikasju','Püsivara võib uuendamise ajal taaskäivituda.'),
 'fa': ('در حال به‌روزرسانی…','به‌روزرسانی کامل شد','به‌روزرسانی ناموفق بود','نمایش جزئیات به‌روزرسانی','ممکن است میان‌افزار هنگام به‌روزرسانی دوباره راه‌اندازی شود.'),
 'fr': ('Mise à jour en cours…','Mise à jour terminée','Échec de la mise à jour','Afficher les détails','Le micrologiciel peut redémarrer pendant la mise à jour.'),
 'he': ('מתבצע עדכון…','העדכון הושלם','העדכון נכשל','הצגת פרטי העדכון','הקושחה עשויה לפעול מחדש במהלך העדכון.'),
 'hr': ('Ažuriranje…','Ažuriranje dovršeno','Ažuriranje nije uspjelo','Prikaži pojedinosti ažuriranja','Firmver se može ponovno pokrenuti tijekom ažuriranja.'),
 'hu': ('Frissítés folyamatban…','Frissítés kész','A frissítés sikertelen','Frissítési részletek','A firmware a frissítés során újraindulhat.'),
 'it': ('Aggiornamento in corso…','Aggiornamento completato','Aggiornamento non riuscito','Mostra dettagli aggiornamento','Il firmware potrebbe riavviarsi durante l’aggiornamento.'),
 'lt': ('Atnaujinama…','Atnaujinimas baigtas','Atnaujinimas nepavyko','Rodyti atnaujinimo informaciją','Atnaujinant programinė aparatinė įranga gali būti paleista iš naujo.'),
 'nl': ('Bijwerken…','Update voltooid','Update mislukt','Updatedetails bekijken','De firmware kan tijdens de update opnieuw opstarten.'),
 'pl': ('Trwa aktualizacja…','Aktualizacja zakończona','Aktualizacja nie powiodła się','Pokaż szczegóły aktualizacji','Podczas aktualizacji oprogramowanie sprzętowe może się ponownie uruchomić.'),
 'pt': ('A atualizar…','Atualização concluída','Falha na atualização','Ver detalhes da atualização','O firmware pode reiniciar durante a atualização.'),
 'pt_BR': ('Atualizando…','Atualização concluída','Falha na atualização','Ver detalhes da atualização','O firmware pode reiniciar durante a atualização.'),
 'rs': ('Ажурирање…','Ажурирање је завршено','Ажурирање није успело','Прикажи детаље ажурирања','Фирмвер се може поново покренути током ажурирања.'),
 'ru': ('Обновление…','Обновление завершено','Ошибка обновления','Показать сведения об обновлении','Во время обновления прошивка может перезапуститься.'),
 'sk': ('Prebieha aktualizácia…','Aktualizácia dokončená','Aktualizácia zlyhala','Zobraziť podrobnosti aktualizácie','Počas aktualizácie sa môže firmvér reštartovať.'),
 'sl': ('Posodabljanje…','Posodobitev končana','Posodobitev ni uspela','Prikaži podrobnosti posodobitve','Vdelana programska oprema se lahko med posodobitvijo znova zažene.'),
 'sv': ('Uppdaterar…','Uppdatering slutförd','Uppdatering misslyckades','Visa uppdateringsinformation','Den fasta programvaran kan startas om under uppdateringen.'),
 'tr': ('Güncelleniyor…','Güncelleme tamamlandı','Güncelleme başarısız','Güncelleme ayrıntılarını göster','Güncelleme sırasında donanım yazılımı yeniden başlatılabilir.'),
 'uk': ('Оновлення…','Оновлення завершено','Помилка оновлення','Показати подробиці оновлення','Під час оновлення мікропрограма може перезапуститися.'),
 'vi': ('Đang cập nhật…','Cập nhật hoàn tất','Cập nhật thất bại','Xem chi tiết cập nhật','Phần sụn có thể khởi động lại trong quá trình cập nhật.'),
}
ROWS['de_formal'] = ROWS['de']
ROWS['zh'] = ROWS['zh_CN']
ROWS['ja'] = ROWS['jp']

def caption(language, key):
    language = str(language).replace('-', '_')
    row = ROWS.get(language, ROWS.get(language.split('_')[0], ROWS['en']))
    return row[KEYS.index(key)]
