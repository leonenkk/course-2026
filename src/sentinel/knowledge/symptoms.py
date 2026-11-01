"""Словарь фраз симптомов для формирования запроса к поиску по идентификаторам сигналов."""
from sentinel.domain import (
    CONSUMER_STALLED,
    ERROR_RATE_HIGH,
    LATENCY_HIGH,
    LOG_DB_CONN,
    LOG_SENSITIVE_DATA,
    QUEUE_GROWING,
    WORKERS_DOWN,
)

SYMPTOMS = {
    WORKERS_DOWN: "воркеры не отвечают число живых воркеров равно нулю процесс завершён",
    QUEUE_GROWING: "длина очереди растёт задачи накапливаются",
    LATENCY_HIGH: "задержка обработки выросла задачи выполняются долго",
    ERROR_RATE_HIGH: "резкий рост доли ошибок",
    CONSUMER_STALLED: "воркеры живы но обработка стоит потребитель заблокирован повторная доставка сообщения",
    LOG_DB_CONN: "исчерпание пула соединений с базой данных PostgreSQL таймаут",
    LOG_SENSITIVE_DATA: "выгрузка персональных данных пользователей на внешний адрес утечка",
}
