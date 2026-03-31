DOCUMENTID_TABLE = "baseapp_core_documentid"


def get_fk_constraints_referencing_table(cursor, table, column, referenced_table):
    """Find FK constraint names on (table, column) that reference the given table."""
    cursor.execute(
        """
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_name = kcu.table_name
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
        WHERE tc.table_name = %s
          AND kcu.column_name = %s
          AND tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_name = %s
        """,
        [table, column, referenced_table],
    )
    return [row[0] for row in cursor.fetchall()]


def replace_fk_constraint(
    schema_editor, cursor, table, column, referenced_table, on_delete_cascade
):
    """
    Drop and recreate a FK constraint with or without ON DELETE CASCADE.

    Raises RuntimeError if no FK constraint is found, since the migration
    dependencies should guarantee the FK exists by the time this runs.
    """
    constraint_names = get_fk_constraints_referencing_table(cursor, table, column, referenced_table)

    if not constraint_names:
        raise RuntimeError(
            f"Expected an FK from {table}.{column} to {referenced_table}, but none was found."
        )

    for constraint_name in constraint_names:
        schema_editor.execute(
            "ALTER TABLE %s DROP CONSTRAINT %s"
            % (
                schema_editor.quote_name(table),
                schema_editor.quote_name(constraint_name),
            )
        )

    new_constraint_name = "%s_%s_fk_%s" % (table, column, referenced_table)
    if len(new_constraint_name) > 63:
        new_constraint_name = new_constraint_name[:63]

    on_delete_clause = "ON DELETE CASCADE " if on_delete_cascade else ""

    schema_editor.execute(
        "ALTER TABLE %s ADD CONSTRAINT %s "
        "FOREIGN KEY (%s) REFERENCES %s (id) "
        "%sDEFERRABLE INITIALLY DEFERRED"
        % (
            schema_editor.quote_name(table),
            schema_editor.quote_name(new_constraint_name),
            schema_editor.quote_name(column),
            schema_editor.quote_name(referenced_table),
            on_delete_clause,
        )
    )
