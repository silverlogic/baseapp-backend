import pgtrigger
import pytest
import swapper

from baseapp_chats.triggers import Func

Message = swapper.load_model("baseapp_chats", "Message")


pytestmark = pytest.mark.django_db(transaction=True)


def test_func_render_compatible_with_pgtrigger_template_kwargs():
    meta = Message._meta
    func = Func(
        "table={meta.db_table} model={model._meta.model_name} field={fields.id.name} column={columns.id}"
    )
    trigger = pgtrigger.Trigger(
        name="test_func_render_uses_kwargs",
        level=pgtrigger.Row,
        when=pgtrigger.Before,
        operation=pgtrigger.Insert,
        func=func,
    )

    rendered = func.render(**trigger.get_func_template_kwargs(Message))

    assert rendered == (f"table={meta.db_table} model={meta.model_name} field=id column=id")
