import graphene

from apps.accounts.schema import Query as AccountsQuery, Mutation as AccountsMutation
from apps.agencies.schema import Query as AgenciesQuery
from apps.drivers.schema import Query as DriversQuery, Mutation as DriversMutation
from apps.onboarding.schema import Query as OnboardingQuery, Mutation as OnboardingMutation
from apps.scheduling.schema import Query as SchedulingQuery, Mutation as SchedulingMutation
from apps.documents.schema import Query as DocumentsQuery, Mutation as DocumentsMutation
from apps.training.schema import Query as TrainingQuery, Mutation as TrainingMutation
from apps.invoicing.schema import Query as InvoicingQuery, Mutation as InvoicingMutation


class Query(
    AccountsQuery,
    AgenciesQuery,
    DriversQuery,
    OnboardingQuery,
    SchedulingQuery,
    DocumentsQuery,
    TrainingQuery,
    InvoicingQuery,
    graphene.ObjectType,
):
    pass


class Mutation(
    AccountsMutation,
    DriversMutation,
    OnboardingMutation,
    SchedulingMutation,
    DocumentsMutation,
    TrainingMutation,
    InvoicingMutation,
    graphene.ObjectType,
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
