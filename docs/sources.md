# Источники инфраструктуры

Инфраструктура подготовлена с помощью ChatGPT/Codex. Доменная реализация
получена из командного репозитория. Это дополнение к журналу; команда должна
дописать источники своей части. Заимствованных готовых compose-рецептов нет.

Официальные материалы, по которым сверялись настройки:

- Patroni YAML, bootstrap, etcd3, pg_rewind:
  https://patroni.readthedocs.io/en/latest/yaml_configuration.html
- Patroni API, /primary, /replica, /cluster:
  https://patroni.readthedocs.io/en/latest/rest_api.html
- Установка Patroni и выбор зависимостей:
  https://patroni.readthedocs.io/en/latest/installation.html
- Закреплённый пакет Patroni 4.1.0:
  https://pypi.org/project/patroni/4.1.0/
- Запуск etcd в контейнерах, официальный registry и тег 3.5.21:
  https://etcd.io/docs/v3.5/op-guide/container/
- PgBouncer, session pooling и хранение паролей:
  https://www.pgbouncer.org/config.html
- HAProxy health checks:
  https://www.haproxy.com/documentation/haproxy-configuration-tutorials/reliability/health-checks/
- PostgreSQL 16 predefined roles (pg_monitor):
  https://www.postgresql.org/docs/16/predefined-roles.html
- PostgreSQL 16 publications:
  https://www.postgresql.org/docs/16/logical-replication-publication.html

Проверка состояла в чтении документации и статическом анализе написанных файлов.
Версии образов, сборка, SQL-права, репликация и failover на практике пока
не проверялись.
