import graphene

from apps.accounts.schema import Query as AccountsQuery, Mutation as AccountsMutation


class Query(AccountsQuery, graphene.ObjectType):
    pass


class Mutation(AccountsMutation, graphene.ObjectType):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
