from django.contrib.auth.models import AnonymousUser
from graphene_file_upload.django import FileUploadGraphQLView


class AuthenticatedGraphQLView(FileUploadGraphQLView):
    """Ensures info.context.user and info.context.current_agency are populated."""

    def get_context(self, request):
        from apps.common.context import get_current_agency
        context = request
        context.user = getattr(request, "user", None) or AnonymousUser()
        context.current_agency = get_current_agency()
        return context

    def execute_graphql_request(self, request, data, query, variables, operation_name, show_graphiql=False):
        request.user = getattr(request, "user", None) or AnonymousUser()
        return super().execute_graphql_request(request, data, query, variables, operation_name, show_graphiql)
