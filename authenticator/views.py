from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, login, get_user_model
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

User = get_user_model()

@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response(
                {"error": "Both email and password are required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Fetch user by email to retrieve their exact username
        try:
            user_obj = User.objects.get(email=email)
            username = user_obj.username
        except User.DoesNotExist:
            username = email  # Fallback in case username is the email

        # 2. Authenticate using the retrieved username
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return Response({
                "message": "Login successful",
                "user_id": user.id,
                "email": user.email
            }, status=status.HTTP_200_OK)
        
        return Response(
            {"error": "Invalid email or password."}, 
            status=status.HTTP_401_UNAUTHORIZED
        )