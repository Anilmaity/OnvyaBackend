import graphene

from apps.accounts.schema import Query as AccountsQuery, Mutation as AccountsMutation
from apps.agencies.schema import Query as AgenciesQuery
from apps.drivers.schema import Query as DriversQuery, Mutation as DriversMutation


class Query(AccountsQuery, AgenciesQuery, DriversQuery, graphene.ObjectType):
    pass


class Mutation(AccountsMutation, DriversMutation, graphene.ObjectType):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
