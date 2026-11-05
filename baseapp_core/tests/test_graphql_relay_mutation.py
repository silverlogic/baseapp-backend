import graphene

from baseapp_core.graphql import RelayMutation


class Greet(RelayMutation):
    greeting = graphene.String()

    class Input:
        name = graphene.String(required=True)

    @classmethod
    def mutate_and_get_payload(cls, root, info, **input) -> "Greet":
        return cls(greeting=f"Hello {input['name']}{input.get('punctuation', '')}")


class GreetWithPunctuation(Greet):
    class Input(Greet.Input):
        punctuation = graphene.String()

    class Meta:
        # The payload's name; the input type is named after it without "Payload".
        name = "GreetPayload"


class GreetAgain(Greet):
    pass


class Query(graphene.ObjectType):
    ok = graphene.Boolean()


def _input_fields(mutation: type[RelayMutation]) -> set[str]:
    class Mutation(graphene.ObjectType):
        run = mutation.Field()

    schema = graphene.Schema(query=Query, mutation=Mutation)
    return set(schema.graphql_schema.get_type(mutation.Input._meta.name).fields)


def test_subclass_extends_the_parent_input_and_keeps_its_name() -> None:
    assert GreetWithPunctuation._meta.name == Greet._meta.name == "GreetPayload"
    assert GreetWithPunctuation.Input._meta.name == Greet.Input._meta.name == "GreetInput"
    assert _input_fields(GreetWithPunctuation) == {"name", "punctuation", "clientMutationId"}


def test_subclass_without_input_reuses_the_parent_input() -> None:
    assert _input_fields(GreetAgain) == {"name", "clientMutationId"}


def test_subclass_mutation_runs_with_the_extra_input() -> None:
    class Mutation(graphene.ObjectType):
        greet = GreetWithPunctuation.Field()

    schema = graphene.Schema(query=Query, mutation=Mutation)
    result = schema.execute(
        'mutation { greet(input: {name: "Ana", punctuation: "!"}) { greeting } }'
    )

    assert result.errors is None
    assert result.data == {"greet": {"greeting": "Hello Ana!"}}
