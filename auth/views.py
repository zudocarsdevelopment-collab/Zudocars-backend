from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, login

class LoginView(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response(
                {"error": "Both email and password are required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Authenticate user
        user = authenticate(request, username=email, password=password)

        if user is not None:
            # Creates session for the user
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