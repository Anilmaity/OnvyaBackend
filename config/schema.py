import graphene

from apps.accounts.schema import Query as AccountsQuery, Mutation as AccountsMutation
from apps.agencies.schema import Query as AgenciesQuery
from apps.drivers.schema import Query as DriversQuery, Mutation as DriversMutation
from apps.onboarding.schema import Query as OnboardingQuery, Mutation as OnboardingMutation


class Query(AccountsQuery, AgenciesQuery, DriversQuery, OnboardingQuery, graphene.ObjectType):
    pass


class Mutation(AccountsMutation, DriversMutation, OnboardingMutation, graphene.ObjectType):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
