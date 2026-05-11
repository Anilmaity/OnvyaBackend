import graphene


class Query(graphene.ObjectType):
    ping = graphene.String()

    def resolve_ping(self, info):
        return "pong"


class Mutation(graphene.ObjectType):
    noop = graphene.String()

    def resolve_noop(self, info):
        return "ok"


schema = graphene.Schema(query=Query, mutation=Mutation)
