import graphene

from apps.accounts.schema import Query as AccountsQuery, Mutation as AccountsMutation
from apps.agencies.schema import Query as AgenciesQuery


class Query(AccountsQuery, AgenciesQuery, graphene.ObjectType):
    pass


class Mutation(AccountsMutation, graphene.ObjectType):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
