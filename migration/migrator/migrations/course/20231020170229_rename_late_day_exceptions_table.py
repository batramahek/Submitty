"""Migration for a given Submitty course database."""


def up(config, database, semester, course):
    """
    Run up migration.

    :param config: Object holding configuration details about Submitty
    :type config: migrator.config.Config
    :param database: Object for interacting with given database for environment
    :type database: migrator.db.Database
    :param semester: Semester of the course being migrated
    :type semester: str
    :param course: Code of course being migrated
    :type course: str
    """

    sql = """ALTER TABLE late_day_exceptions RENAME TO excused_absence_extensions;
            ALTER TABLE excused_absence_extensions RENAME COLUMN late_day_exceptions TO excused_absence_extensions;
            ALTER TABLE late_day_cache RENAME COLUMN late_day_exceptions TO excused_absence_extensions;"""
    database.execute(sql)

    pass


def down(config, database, semester, course):
    """
    Run down migration (rollback).

    :param config: Object holding configuration details about Submitty
    :type config: migrator.config.Config
    :param database: Object for interacting with given database for environment
    :type database: migrator.db.Database
    :param semester: Semester of the course being migrated
    :type semester: str
    :param course: Code of course being migrated
    :type course: 
    """

    sql = """ALTER TABLE excused_absence_extensions RENAME TO late_day_exceptions;
            ALTER TABLE late_day_exceptions RENAME COLUMN excused_absence_extensions TO late_day_exceptions;
            ALTER TABLE late_day_cache RENAME COLUMN excused_absence_extensions TO late_day_exceptions;"""
    database.execute(sql)

    pass
