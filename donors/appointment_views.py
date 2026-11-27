from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCoordinator

from . import appointments, coordinator_appointments
from .appointment_serializers import (
    AppointmentRecordSerializer,
    AppointmentSearchSerializer,
    AppointmentWriteSerializer,
    StartAppointmentSerializer,
)
from .permissions import IsDonor
from .serializers import DeleteConfirmationSerializer


class CanManageOwnAppointments(IsDonor):
    message = "Only donors can access their own appointments here."


class MyAppointmentListView(APIView):
    permission_classes = [IsAuthenticated, CanManageOwnAppointments]

    def get(self, request):
        return Response(appointments.list_appointments(request.user.pk))

    def post(self, request):
        data = AppointmentWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(
            appointments.save_booking(request.user.pk, data.validated_data),
            status=status.HTTP_201_CREATED,
        )


class MyAppointmentDetailView(APIView):
    permission_classes = [IsAuthenticated, CanManageOwnAppointments]

    def get(self, request, appointment_id):
        return Response(appointments.get_appointment(request.user.pk, appointment_id))

    def patch(self, request, appointment_id):
        data = AppointmentWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        return Response(appointments.save_booking(
            request.user.pk, data.validated_data, appointment_id=appointment_id
        ))


class MyAppointmentCancelView(APIView):
    permission_classes = [IsAuthenticated, CanManageOwnAppointments]

    def post(self, request, appointment_id):
        data = DeleteConfirmationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(appointments.cancel_booking(request.user.pk, appointment_id))


class CoordinatorAppointmentListView(APIView):
    permission_classes = [IsAuthenticated, IsCoordinator]

    def get(self, request):
        params = AppointmentSearchSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        return Response(coordinator_appointments.list_appointments(
            request.user, params.validated_data
        ))


class CoordinatorAppointmentStartView(APIView):
    permission_classes = [IsAuthenticated, IsCoordinator]

    def post(self, request, appointment_id):
        params = StartAppointmentSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        return Response(coordinator_appointments.start_appointment(request.user, appointment_id))


class CoordinatorAppointmentRecordView(APIView):
    permission_classes = [IsAuthenticated, IsCoordinator]

    def post(self, request, appointment_id):
        data = AppointmentRecordSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(
            coordinator_appointments.record_appointment(
                request.user, appointment_id, data.validated_data
            ),
            status=status.HTTP_201_CREATED,
        )


class CoordinatorAppointmentCancelView(APIView):
    permission_classes = [IsAuthenticated, IsCoordinator]

    def post(self, request, appointment_id):
        data = DeleteConfirmationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(coordinator_appointments.cancel_appointment(request.user, appointment_id))
