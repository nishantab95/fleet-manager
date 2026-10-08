import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import 'data/api_client.dart';
import 'data/secure_session_store.dart';
import 'data/sync_engine.dart';
import 'domain/driver_models.dart';
import 'domain/role_models.dart';
import 'fleet_theme.dart';
import 'pilot_update.dart';
import 'role_screens.dart';

const appVersion = String.fromEnvironment(
  'FLUTTER_BUILD_NAME',
  defaultValue: '0.1.0',
);
const appBuild = String.fromEnvironment(
  'FLUTTER_BUILD_NUMBER',
  defaultValue: '1',
);
const maxOdometerKm = 10000000.0;
const invalidOdometerMessage =
    'KM reading looks invalid. Please check the odometer and enter the correct value.';
const maxHourMeterHours = 1000000.0;
const invalidHourMeterMessage =
    'HMR looks invalid. Please check the hour meter and enter the correct value.';
const deviceHandoverBlockedMessage =
    'This phone still has an active duty or unsynced records for another '
    'driver. Finish and sync that work before changing driver.';

class DriverAppDependencies {
  const DriverAppDependencies({
    required this.api,
    required this.sessionStore,
    required this.sync,
    required this.installationIdentifier,
    this.pilotUpdater,
  });

  final ApiClient api;
  final SecureSessionStore sessionStore;
  final SyncEngine sync;
  final String installationIdentifier;
  final PilotUpdateController? pilotUpdater;

  Future<void> registerDriverAccount(
    SessionTokens tokens, {
    bool allowOffline = false,
  }) async {
    if (allowOffline) {
      await sync.activateAccount(
        serverIdentity: api.baseUrl,
        companyId: tokens.companyId,
        membershipId: tokens.membershipId,
        claimLegacyData: true,
      );
    }
    try {
      await api.registerDevice(installationIdentifier: installationIdentifier);
    } on ApiException catch (error) {
      if (allowOffline && error.isRetryable) return;
      if (error.code != 'DEVICE_HANDOVER_REQUIRED') rethrow;
      final oldMembershipId =
          error.context?['current_membership_id'] as String?;
      if (oldMembershipId == null || oldMembershipId.isEmpty) rethrow;
      final safety = await sync.prepareHandover(
        serverIdentity: api.baseUrl,
        companyId: tokens.companyId,
        oldMembershipId: oldMembershipId,
      );
      if (!safety.isSafe) {
        throw const ApiException(
          409,
          deviceHandoverBlockedMessage,
          code: 'LOCAL_DEVICE_HANDOVER_BLOCKED',
        );
      }
      await api.registerDevice(
        installationIdentifier: installationIdentifier,
        allowHandover: true,
        localStateClear: true,
      );
    }
    if (!allowOffline) {
      await sync.activateAccount(
        serverIdentity: api.baseUrl,
        companyId: tokens.companyId,
        membershipId: tokens.membershipId,
        claimLegacyData: true,
      );
    }
  }
}

class FleetManagerApp extends StatelessWidget {
  const FleetManagerApp({super.key, this.dependencies});

  final DriverAppDependencies? dependencies;

  @override
  Widget build(BuildContext context) {
    final home = dependencies == null
        ? const _UnavailableScreen()
        : DriverSessionScreen(dependencies: dependencies!);
    return MaterialApp(
      title: isPilotBuild ? 'Fleet Manager Pilot' : 'Fleet Manager',
      theme: fleetTheme(),
      home: dependencies?.pilotUpdater == null
          ? home
          : PilotUpdateGate(
              controller: dependencies!.pilotUpdater!,
              child: home,
            ),
    );
  }
}

class DriverSessionScreen extends StatefulWidget {
  const DriverSessionScreen({required this.dependencies, super.key});

  final DriverAppDependencies dependencies;

  @override
  State<DriverSessionScreen> createState() => _DriverSessionScreenState();
}

class _DriverSessionScreenState extends State<DriverSessionScreen>
    with WidgetsBindingObserver {
  DriverAssignment? _assignment;
  DriverDutyState _duty = const DriverDutyState.none();
  String? _role;
  bool _loading = true;
  String? _error;
  Future<String?>? _driverRefreshInFlight;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.dependencies.api.setSessionExpiredHandler(_sessionExpired);
    unawaited(_restoreSession());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.dependencies.api.setSessionExpiredHandler(null);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed &&
        !_loading &&
        widget.dependencies.api.session?.role == 'DRIVER') {
      unawaited(_refreshDriverState());
    }
  }

  Future<void> _sessionExpired() async {
    try {
      await widget.dependencies.sessionStore.clear();
    } on Object {
      // Continue to a safe signed-out UI even if secure-storage cleanup fails.
    }
    widget.dependencies.api.clearSession();
    widget.dependencies.sync.deactivateAccount();
    if (!mounted) return;
    Navigator.of(context).popUntil((route) => route.isFirst);
    setState(() {
      _assignment = null;
      _duty = const DriverDutyState.none();
      _role = null;
      _error = sessionExpiredMessage;
    });
  }

  Future<void> _restoreSession() async {
    final api = widget.dependencies.api;
    if (api.session == null) {
      if (mounted) setState(() => _loading = false);
      return;
    }
    try {
      DriverAssignment? assignment;
      var duty = const DriverDutyState.none();
      if (api.session?.role == 'DRIVER') {
        await widget.dependencies.registerDriverAccount(
          api.session!,
          allowOffline: true,
        );
        final state = await widget.dependencies.sync.reconcileDriverState();
        assignment = state.assignment;
        duty = state.duty;
      } else {
        await api.validateSession();
      }
      if (mounted) {
        setState(() {
          _assignment = assignment;
          _duty = duty;
          _role = api.session?.role;
        });
      }
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await _sessionExpired();
      } else if (mounted) {
        if (api.session?.role == 'DRIVER') {
          await widget.dependencies.sessionStore.clear();
          api.clearSession();
          widget.dependencies.sync.deactivateAccount();
        }
        setState(() {
          _role = null;
          _error = error.message;
        });
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _signedIn(SessionTokens tokens) async {
    DriverAssignment? assignment;
    var duty = const DriverDutyState.none();
    if (tokens.role == 'DRIVER') {
      final state = await widget.dependencies.sync.reconcileDriverState();
      assignment = state.assignment;
      duty = state.duty;
    }
    if (!mounted) return;
    setState(() {
      _assignment = assignment;
      _duty = duty;
      _role = tokens.role;
      _error = null;
    });
  }

  Future<String?> _refreshDriverState() {
    final active = _driverRefreshInFlight;
    if (active != null) return active;
    final refresh = _performDriverStateRefresh();
    _driverRefreshInFlight = refresh;
    return refresh.whenComplete(() {
      if (identical(_driverRefreshInFlight, refresh)) {
        _driverRefreshInFlight = null;
      }
    });
  }

  Future<String?> _performDriverStateRefresh() async {
    try {
      final state = await widget.dependencies.sync.reconcileDriverState();
      if (mounted) {
        setState(() {
          _assignment = state.assignment;
          _duty = state.duty;
        });
      }
      return state.warning;
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await _sessionExpired();
      }
      return error.message;
    }
  }

  Future<void> _signOut() async {
    try {
      await widget.dependencies.api.logout();
    } on ApiException {
      // Local credentials are cleared even when the device is offline.
      widget.dependencies.api.clearSession();
    }
    await widget.dependencies.sessionStore.clear();
    widget.dependencies.api.clearSession();
    widget.dependencies.sync.deactivateAccount();
    if (mounted) {
      setState(() {
        _assignment = null;
        _duty = const DriverDutyState.none();
        _role = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (widget.dependencies.api.session == null) {
      return LoginScreen(
        dependencies: widget.dependencies,
        initialError: _error,
        onSignedIn: _signedIn,
      );
    }
    return switch (_role ?? widget.dependencies.api.session?.role) {
      'SUPERVISOR' => SupervisorHomeScreen(
        api: widget.dependencies.api,
        onSignOut: _signOut,
      ),
      'OWNER_ADMIN' => OwnerHomeScreen(
        api: widget.dependencies.api,
        onSignOut: _signOut,
      ),
      _ => DriverHomeScreen(
        dependencies: widget.dependencies,
        assignment: _assignment,
        duty: _duty,
        onRefreshState: _refreshDriverState,
        onSignOut: _signOut,
      ),
    };
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    required this.dependencies,
    required this.onSignedIn,
    this.initialError,
    super.key,
  });

  final DriverAppDependencies dependencies;
  final Future<void> Function(SessionTokens) onSignedIn;
  final String? initialError;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _phoneController = TextEditingController();
  final _otpController = TextEditingController();
  String? _challengeId;
  String? _preSessionToken;
  List<MembershipOption> _memberships = const [];
  String _selectedRole = 'DRIVER';
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _error = widget.initialError;
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  Future<void> _requestOtp() async {
    await _run(() async {
      _challengeId = await widget.dependencies.api.requestOtp(
        _phoneController.text.trim(),
        requestedRole: _selectedRole,
      );
    });
  }

  Future<void> _verifyOtp() async {
    final challengeId = _challengeId;
    if (challengeId == null) return;
    await _run(() async {
      _preSessionToken = await widget.dependencies.api.verifyOtp(
        challengeId: challengeId,
        otp: _otpController.text.trim(),
      );
      final memberships = await widget.dependencies.api.memberships(
        _preSessionToken!,
      );
      _memberships = memberships
          .where((item) => item.role == _selectedRole)
          .toList();
      if (_memberships.length == 1) {
        await _selectMembership(_memberships.single);
      }
      if (mounted) setState(() {});
    });
  }

  Future<void> _selectMembership(MembershipOption membership) async {
    final tokens = await widget.dependencies.api.createSession(
      preSessionToken: _preSessionToken!,
      membershipId: membership.membershipId,
    );
    try {
      if (tokens.role == 'DRIVER') {
        await widget.dependencies.registerDriverAccount(tokens);
      }
      await widget.dependencies.sessionStore.save(tokens);
    } on Object {
      await widget.dependencies.sessionStore.clear();
      widget.dependencies.api.clearSession();
      widget.dependencies.sync.deactivateAccount();
      rethrow;
    }
    await widget.onSignedIn(tokens);
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasChallenge = _challengeId != null;
    final hasMembershipChoice = _memberships.isNotEmpty;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Fleet Manager'),
        actions: isPilotBuild
            ? [
                IconButton(
                  tooltip: 'Server settings',
                  icon: const Icon(Icons.settings_outlined),
                  onPressed: () => _showPilotServerSettings(context),
                ),
              ]
            : null,
      ),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Row(
            children: [
              if (isPilotBuild)
                Text(
                  'PILOT / TEST',
                  style: Theme.of(context).textTheme.labelLarge,
                ),
              const Spacer(),
              Flexible(
                child: Text(
                  widget.dependencies.api.baseUrl,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.end,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Text('Sign in', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 6),
          const Text(
            'Choose your role, then use your registered phone number.',
          ),
          const SizedBox(height: 20),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(
                value: 'DRIVER',
                label: Text('DRIVER'),
                icon: Icon(Icons.drive_eta),
              ),
              ButtonSegment(
                value: 'SUPERVISOR',
                label: Text('SUPERVISOR'),
                icon: Icon(Icons.fact_check_outlined),
              ),
              ButtonSegment(
                value: 'OWNER_ADMIN',
                label: Text('OWNER'),
                icon: Icon(Icons.dashboard_outlined),
              ),
            ],
            selected: {_selectedRole},
            onSelectionChanged: _busy
                ? null
                : (value) => setState(() {
                    _selectedRole = value.first;
                    _challengeId = null;
                    _memberships = const [];
                  }),
          ),
          const SizedBox(height: 18),
          TextField(
            controller: _phoneController,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(labelText: 'Phone number'),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: _busy ? null : _requestOtp,
            child: const Text('SEND OTP'),
          ),
          if (hasChallenge) ...[
            const SizedBox(height: 20),
            TextField(
              controller: _otpController,
              keyboardType: TextInputType.number,
              maxLength: 6,
              decoration: const InputDecoration(labelText: 'One-time password'),
            ),
            FilledButton(
              onPressed: _busy ? null : _verifyOtp,
              child: const Text('CONTINUE'),
            ),
          ],
          if (hasMembershipChoice) ...[
            const SizedBox(height: 20),
            const Text('Choose your company'),
            for (final membership in _memberships)
              ListTile(
                title: Text(membership.companyName),
                subtitle: Text(membership.role),
                onTap: _busy
                    ? null
                    : () => _run(() => _selectMembership(membership)),
              ),
          ],
          if (_error != null) ...[
            const SizedBox(height: 16),
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _showPilotServerSettings(BuildContext context) async {
    final controller = TextEditingController(
      text: widget.dependencies.api.baseUrl,
    );
    var message = '';
    var testing = false;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Pilot settings'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: controller,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'Server URL',
                  hintText: 'http://192.168.1.20:8000',
                ),
              ),
              const SizedBox(height: 16),
              const Divider(),
              const ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('Fleet Manager Pilot'),
                subtitle: Text('Version $appVersion · Build $appBuild'),
              ),
              if (widget.dependencies.pilotUpdater != null)
                Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton.icon(
                    onPressed: testing
                        ? null
                        : () async {
                            Navigator.pop(dialogContext);
                            await widget.dependencies.pilotUpdater!
                                .checkAndPresent(this.context, manual: true);
                          },
                    icon: const Icon(Icons.system_update_alt),
                    label: const Text('CHECK FOR UPDATES'),
                  ),
                ),
              if (message.isNotEmpty) ...[
                const SizedBox(height: 10),
                Text(message),
              ],
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('CANCEL'),
            ),
            OutlinedButton(
              onPressed: testing
                  ? null
                  : () async {
                      setDialogState(() => testing = true);
                      try {
                        widget.dependencies.api.setBaseUrl(controller.text);
                        final connected = await widget.dependencies.api
                            .testConnection();
                        setDialogState(
                          () => message = connected
                              ? 'Connected to Fleet Manager server.'
                              : 'Cannot reach Fleet Manager server.',
                        );
                      } on FormatException catch (error) {
                        setDialogState(() => message = error.message);
                      } finally {
                        setDialogState(() => testing = false);
                      }
                    },
              child: Text(testing ? 'TESTING…' : 'TEST CONNECTION'),
            ),
            FilledButton(
              onPressed: () async {
                try {
                  widget.dependencies.api.setBaseUrl(controller.text);
                  await widget.dependencies.sessionStore.savePilotBaseUrl(
                    widget.dependencies.api.baseUrl,
                  );
                  if (dialogContext.mounted) Navigator.pop(dialogContext);
                  if (mounted) setState(() {});
                } on FormatException catch (error) {
                  setDialogState(() => message = error.message);
                }
              },
              child: const Text('SAVE'),
            ),
          ],
        ),
      ),
    );
    controller.dispose();
  }
}

class DriverHomeScreen extends StatefulWidget {
  const DriverHomeScreen({
    required this.dependencies,
    required this.assignment,
    this.duty = const DriverDutyState.none(),
    this.onRefreshState,
    required this.onSignOut,
    super.key,
  });

  final DriverAppDependencies dependencies;
  final DriverAssignment? assignment;
  final DriverDutyState duty;
  final Future<String?> Function()? onRefreshState;
  final Future<void> Function() onSignOut;

  @override
  State<DriverHomeScreen> createState() => _DriverHomeScreenState();
}

class _DriverHomeScreenState extends State<DriverHomeScreen> {
  final _picker = ImagePicker();
  Timer? _syncRetryTimer;
  Timer? _messageTimer;
  int _pendingCount = 0;
  late DriverDutyState _duty;
  String? _message;
  bool _busy = false;
  DateTime? _lastQueuedAt;
  DriverEventType? _lastQueuedEventType;
  List<DriverMaintenanceItem> _maintenanceItems = const [];
  bool _maintenanceLoading = false;

  @override
  void initState() {
    super.initState();
    _duty = widget.duty;
    unawaited(_refreshQueue());
    unawaited(_syncQueuedEvents());
    unawaited(_refreshMaintenance());
  }

  @override
  void dispose() {
    _syncRetryTimer?.cancel();
    _messageTimer?.cancel();
    super.dispose();
  }

  void _showMessage(String message, {bool persistent = false}) {
    if (!mounted) return;
    _messageTimer?.cancel();
    setState(() => _message = message);
    if (persistent) return;
    _messageTimer = Timer(const Duration(seconds: 6), () {
      if (mounted) setState(() => _message = null);
    });
  }

  @override
  void didUpdateWidget(covariant DriverHomeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.duty.status != widget.duty.status ||
        oldWidget.duty.sessionId != widget.duty.sessionId ||
        oldWidget.duty.localState != widget.duty.localState) {
      _duty = widget.duty;
    }
    if (oldWidget.assignment?.assignmentId != widget.assignment?.assignmentId ||
        oldWidget.assignment?.companyMaintenanceManaged !=
            widget.assignment?.companyMaintenanceManaged) {
      unawaited(_refreshMaintenance());
    }
  }

  Future<void> _refreshMaintenance() async {
    final assignment = widget.assignment;
    if (assignment == null || assignment.companyMaintenanceManaged != true) {
      await widget.dependencies.sync.cacheDueMaintenance(
        const [],
        assignmentId: assignment?.assignmentId,
      );
      if (mounted) setState(() => _maintenanceItems = const []);
      return;
    }
    if (mounted) setState(() => _maintenanceLoading = true);
    try {
      final items = await widget.dependencies.api.driverDueMaintenance();
      await widget.dependencies.sync.cacheDueMaintenance(
        items,
        assignmentId: assignment.assignmentId,
      );
      if (mounted) setState(() => _maintenanceItems = items);
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await widget.onSignOut();
        return;
      }
      final cached = await widget.dependencies.sync.localDueMaintenance(
        assignmentId: assignment.assignmentId,
      );
      if (mounted) setState(() => _maintenanceItems = cached);
    } finally {
      if (mounted) setState(() => _maintenanceLoading = false);
    }
  }

  Future<void> _refreshDuty() async {
    try {
      var duty = await widget.dependencies.api.currentDuty();
      final assignment = widget.assignment;
      if (assignment != null) {
        duty = await widget.dependencies.sync.effectiveDuty(
          assignment.assignmentId,
          duty,
        );
      }
      if (mounted) setState(() => _duty = duty);
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await widget.onSignOut();
        return;
      }
      final assignment = widget.assignment;
      if (assignment == null) return;
      final localDuty = await widget.dependencies.sync.localDutyState(
        assignment.assignmentId,
      );
      if (localDuty.localState != null && mounted) {
        setState(() => _duty = localDuty);
      }
    }
  }

  Future<void> _refreshQueue() async {
    final count = await widget.dependencies.sync.pendingCount();
    if (mounted) setState(() => _pendingCount = count);
  }

  Future<void> _sync() async {
    setState(() => _busy = true);
    try {
      await widget.dependencies.sync.syncPending();
      await _refreshQueue();
      final refreshWarning = await _refreshAuthoritativeState();
      final syncError = await widget.dependencies.sync.lastSyncErrorMessage();
      final pending = await widget.dependencies.sync.pendingCount();
      if (mounted) {
        _showMessage(
          refreshWarning ??
              (pending > 0
                  ? (syncError == null
                        ? '$pending event(s) pending. Retry when connected.'
                        : 'Needs attention: $syncError')
                  : 'Synced'),
          persistent: refreshWarning != null || pending > 0,
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<String?> _refreshAuthoritativeState() async {
    final refresh = widget.onRefreshState;
    if (refresh != null) return refresh();
    await _refreshDuty();
    await _refreshMaintenance();
    return null;
  }

  Future<String?> _queue(
    DriverEventType eventType, {
    Map<String, dynamic> payload = const <String, dynamic>{},
    String? evidencePath,
  }) async {
    if (_busy) return null;
    final assignment = widget.assignment;
    if (assignment == null) return null;
    final now = DateTime.now();
    if (_lastQueuedEventType == eventType &&
        _lastQueuedAt != null &&
        now.difference(_lastQueuedAt!) < const Duration(milliseconds: 500)) {
      return null;
    }
    _lastQueuedAt = now;
    _lastQueuedEventType = eventType;
    setState(() => _busy = true);
    try {
      final eventId = await widget.dependencies.sync.enqueue(
        assignment: assignment,
        eventType: eventType,
        payload: payload,
        evidencePath: evidencePath,
      );
      await _refreshQueue();
      if (eventType == DriverEventType.kmReading ||
          eventType == DriverEventType.hmrReading ||
          eventType == DriverEventType.meterCapture) {
        await _refreshDuty();
      }
      if (mounted) {
        final label = switch (eventType) {
          DriverEventType.tripComplete => 'Trip recorded',
          DriverEventType.diesel => 'Diesel recorded',
          DriverEventType.emergency =>
            'Emergency saved on phone — not yet delivered',
          DriverEventType.kmReading => 'KM reading saved',
          DriverEventType.hmrReading => 'HMR saved',
          DriverEventType.meterCapture => 'KM + HMR readings saved',
          DriverEventType.maintenanceProof =>
            'Maintenance proof saved for Supervisor review',
        };
        _showMessage(label);
      }
      unawaited(
        _syncQueuedEvents(
          emergencyEventId: eventType == DriverEventType.emergency
              ? eventId
              : null,
        ),
      );
      return eventId;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _syncQueuedEvents({String? emergencyEventId}) async {
    if (widget.dependencies.api.session == null) return;
    try {
      await widget.dependencies.sync.syncPending();
      await _refreshQueue();
      final refreshWarning = await _refreshAuthoritativeState();
      if (refreshWarning != null && mounted) {
        _showMessage(refreshWarning, persistent: true);
      }
      if (emergencyEventId != null && mounted) {
        final state = await widget.dependencies.sync.eventSyncState(
          emergencyEventId,
        );
        if (state == SyncState.synced.name) {
          _showMessage('Emergency received by server');
        }
      }
    } catch (_) {
      // Offline queue errors remain visible through the pending count and
      // diagnostics; the local operational state must stay available.
    } finally {
      await _scheduleAutomaticRetryIfUseful();
    }
  }

  Future<void> _scheduleAutomaticRetryIfUseful() async {
    if (!mounted || await widget.dependencies.sync.pendingCount() == 0) {
      _syncRetryTimer?.cancel();
      _syncRetryTimer = null;
      return;
    }
    final category = await widget.dependencies.sync.lastSyncErrorCategory();
    const retryableCategories = {
      'BACKEND_UNAVAILABLE',
      'RETRY_LATER',
      'LOCAL_OR_NETWORK_ERROR',
      'AUTH_REQUIRED',
    };
    if (category != null && !retryableCategories.contains(category)) return;
    if (_syncRetryTimer?.isActive == true) return;
    _syncRetryTimer = Timer(const Duration(seconds: 15), () {
      _syncRetryTimer = null;
      unawaited(_syncQueuedEvents());
    });
  }

  Future<void> _showKmDialog({KmReadingType? forcedType}) async {
    final type = forcedType ?? await _chooseReadingType(hourMeter: false);
    if (type == null || !mounted) return;
    final result = await showDialog<_KmCapture>(
      context: context,
      builder: (context) => _KmDialog(type: type),
    );
    if (result == null) {
      return;
    }
    final photo = await _pickEvidence(mustChoose: true);
    if (photo == null) {
      return;
    }
    if (_duty.canCorrectStart && result.type == KmReadingType.startReading) {
      await _correctStart(result.value, photo.path, hourMeter: false);
      return;
    }
    await _queue(
      DriverEventType.kmReading,
      payload: {
        'reading_type': result.type.wireName,
        'reading_value': result.value,
      },
      evidencePath: photo.path,
    );
  }

  Future<void> _showHmrDialog({KmReadingType? forcedType}) async {
    final type = forcedType ?? await _chooseReadingType(hourMeter: true);
    if (type == null || !mounted) return;
    final result = await showDialog<_KmCapture>(
      context: context,
      builder: (context) => _KmDialog(type: type, hourMeter: true),
    );
    if (result == null) return;
    final photo = await _pickEvidence(mustChoose: true);
    if (photo == null) return;
    if (_duty.canCorrectStart && result.type == KmReadingType.startReading) {
      await _correctStart(result.value, photo.path, hourMeter: true);
      return;
    }
    await _queue(
      DriverEventType.hmrReading,
      payload: {
        'reading_type': result.type.wireName,
        'reading_value': result.value,
      },
      evidencePath: photo.path,
    );
  }

  Future<void> _showDualMeterDialog({KmReadingType? forcedType}) async {
    final type = forcedType ?? await _chooseReadingType(hourMeter: false);
    if (type == null || !mounted) return;
    final result = await showDialog<_DualMeterCapture>(
      context: context,
      builder: (context) => _DualMeterDialog(type: type),
    );
    if (result == null) return;
    final kmPhoto = await _pickEvidence(mustChoose: true);
    if (kmPhoto == null) return;
    final hmrPhoto = await _pickEvidence(mustChoose: true);
    if (hmrPhoto == null) return;
    final assignment = widget.assignment;
    if (assignment == null) return;
    if (_duty.canCorrectStart && type == KmReadingType.startReading) {
      setState(() => _busy = true);
      try {
        await widget.dependencies.sync.correctMeterCapture(
          assignmentId: assignment.assignmentId,
          odometerKm: result.odometerKm,
          hourMeter: result.hourMeter,
          kmEvidencePath: kmPhoto.path,
          hmrEvidencePath: hmrPhoto.path,
        );
        await _refreshQueue();
        await _refreshDuty();
        if (mounted) _showMessage('Corrected START KM + HMR saved on phone');
        unawaited(_syncQueuedEvents());
      } finally {
        if (mounted) setState(() => _busy = false);
      }
      return;
    }
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await widget.dependencies.sync.enqueueMeterCapture(
        assignment: assignment,
        readingType: type,
        odometerKm: result.odometerKm,
        hourMeter: result.hourMeter,
        kmEvidencePath: kmPhoto.path,
        hmrEvidencePath: hmrPhoto.path,
      );
      await _refreshQueue();
      await _refreshDuty();
      if (mounted) _showMessage('KM + HMR readings saved');
      unawaited(_syncQueuedEvents());
      _lastQueuedAt = DateTime.now();
      _lastQueuedEventType = DriverEventType.meterCapture;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<KmReadingType?> _chooseReadingType({required bool hourMeter}) async {
    if (!_duty.canCorrectStart) {
      return _duty.canEnd
          ? KmReadingType.endReading
          : KmReadingType.startReading;
    }
    if (!_duty.canEnd) return KmReadingType.startReading;
    return showDialog<KmReadingType>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(hourMeter ? 'HMR READING' : 'KM READING'),
        content: Text(
          'Correct the rejected START ${hourMeter ? 'HMR' : 'KM'}, or record '
          'END ${hourMeter ? 'HMR' : 'KM'} while preserving the correction queue.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('CANCEL'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, KmReadingType.endReading),
            child: Text(hourMeter ? 'END HMR' : 'END KM'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, KmReadingType.startReading),
            child: const Text('CORRECT START'),
          ),
        ],
      ),
    );
  }

  Future<void> _correctStart(
    String readingValue,
    String evidencePath, {
    required bool hourMeter,
  }) async {
    final assignment = widget.assignment;
    if (_busy || assignment == null) return;
    setState(() => _busy = true);
    try {
      await widget.dependencies.sync.correctStart(
        assignmentId: assignment.assignmentId,
        readingValue: readingValue,
        evidencePath: evidencePath,
        hourMeter: hourMeter,
      );
      await _refreshQueue();
      await _refreshDuty();
      if (mounted) {
        _showMessage(
          'Corrected START ${hourMeter ? 'HMR' : 'KM'} saved on phone',
        );
      }
      unawaited(_syncQueuedEvents());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _showDieselDialog() async {
    final litres = await showDialog<String>(
      context: context,
      builder: (context) => const _DieselDialog(),
    );
    if (litres == null) {
      return;
    }
    final photo = await _pickEvidence(mustChoose: false);
    await _queue(
      DriverEventType.diesel,
      payload: {'litres': litres},
      evidencePath: photo?.path,
    );
  }

  Future<void> _showMaintenanceItem(DriverMaintenanceItem item) async {
    final addPhoto = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(item.taskLabel.toUpperCase()),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Status: ${item.status.replaceAll('_', ' ')}'),
            const SizedBox(height: 16),
            const Text('Upload service photos'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('CANCEL'),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.pop(context, true),
            icon: const Icon(Icons.add_a_photo_outlined),
            label: const Text('+ ADD PHOTO'),
          ),
        ],
      ),
    );
    if (addPhoto != true || !mounted) return;
    final photo = await _pickEvidence(mustChoose: true);
    if (photo == null || !mounted) return;
    final submit = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(item.taskLabel.toUpperCase()),
        content: const Text(
          '1 service photo attached. A Supervisor must confirm the service before the next interval is calculated.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('CANCEL'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('SUBMIT FOR SUPERVISOR REVIEW'),
          ),
        ],
      ),
    );
    if (submit != true) return;
    final queued = await _queue(
      DriverEventType.maintenanceProof,
      payload: {'schedule_id': item.scheduleId},
      evidencePath: photo.path,
    );
    if (queued != null && mounted) {
      setState(
        () => _maintenanceItems = _maintenanceItems
            .where((entry) => entry.scheduleId != item.scheduleId)
            .toList(),
      );
      await widget.dependencies.sync.cacheDueMaintenance(
        _maintenanceItems,
        assignmentId: widget.assignment?.assignmentId,
      );
    }
  }

  Future<void> _confirmTripComplete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Mark this trip as completed?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('NO'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('YES'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await _queue(DriverEventType.tripComplete);
    }
  }

  Future<void> _sendEmergency() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Send emergency alert?'),
        content: const Text(
          'The alert will be saved on this phone first and delivered when a connection is available.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('NO'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('SEND'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await _queue(DriverEventType.emergency);
    }
  }

  Future<XFile?> _pickEvidence({required bool mustChoose}) async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      builder: (context) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: const Text('Take Photo'),
              onTap: () => Navigator.pop(context, ImageSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Choose Existing Photo'),
              onTap: () => Navigator.pop(context, ImageSource.gallery),
            ),
            if (!mustChoose)
              ListTile(
                leading: const Icon(Icons.skip_next_outlined),
                title: const Text('Continue Without Photo'),
                onTap: () => Navigator.pop(context),
              ),
          ],
        ),
      ),
    );
    if (source == null) return null;
    try {
      return await _picker.pickImage(source: source, imageQuality: 85);
    } on PlatformException catch (error) {
      if (mounted) {
        _showMessage(
          error.code == 'camera_access_denied'
              ? 'Camera permission is required to take the meter photograph.'
              : 'Photo could not be opened. Please try again.',
        );
      }
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final assignment = widget.assignment;
    final capabilities =
        assignment?.capabilities ?? DriverAssetCapabilities.tipper;
    final hourMeter = capabilities.supportsHourMeter;
    final odometer = capabilities.supportsOdometer;
    final dualMeter = odometer && hourMeter;
    final meterLabel = dualMeter
        ? 'KM + HMR'
        : hourMeter
        ? 'HMR'
        : 'KM';
    final canCapture = assignment != null;
    final dutyActive = _duty.isOperationallyActive;
    final canOperate = canCapture && !_busy && dutyActive;
    final canReadMeter = canCapture && !_busy && _duty.canReadKm;
    final dutyStatusLabel = dutyActive ? 'DUTY ACTIVE' : 'OFF DUTY';
    final dutyDetail = switch (_duty.localState) {
      LocalDutyState.startPendingSync => 'Start saved on phone · Syncing',
      LocalDutyState.activeConfirmed => 'Shift in progress',
      LocalDutyState.endPendingSync => 'Saving end $meterLabel…',
      LocalDutyState.closedConfirmed => 'Previous duty completed',
      LocalDutyState.needsAttention =>
        'START $meterLabel needs correction. Please check the reading.',
      null => switch (_duty.status) {
        DriverDutyStatus.none => 'Ready to start with $meterLabel',
        DriverDutyStatus.active => 'Shift in progress',
        DriverDutyStatus.closed => 'Previous duty completed',
      },
    };
    return Scaffold(
      appBar: AppBar(
        title: const Text('Driver operations'),
        actions: [
          IconButton(
            tooltip: 'Sync',
            onPressed: _busy ? null : _sync,
            icon: const Icon(Icons.sync),
          ),
          IconButton(
            tooltip: 'Diagnostics',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) =>
                    DriverDiagnosticsScreen(dependencies: widget.dependencies),
              ),
            ),
            icon: const Icon(Icons.info_outline),
          ),
          IconButton(
            tooltip: 'Sign out',
            onPressed: widget.onSignOut,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 28),
        children: [
          _AssignmentCard(assignment: assignment),
          const SizedBox(height: 12),
          _DriverStatePanel(
            dutyStatusLabel: dutyStatusLabel,
            dutyDetail: dutyDetail,
            siteName: assignment?.siteName,
            pendingCount: _pendingCount,
            correctionLabel: _duty.canCorrectStart
                ? 'CORRECT START $meterLabel'
                : null,
            onCorrectStart: _duty.canCorrectStart && canReadMeter
                ? () => dualMeter
                      ? _showDualMeterDialog(
                          forcedType: KmReadingType.startReading,
                        )
                      : hourMeter
                      ? _showHmrDialog(forcedType: KmReadingType.startReading)
                      : _showKmDialog(forcedType: KmReadingType.startReading)
                : null,
          ),
          const SizedBox(height: 16),
          if (!dutyActive) ...[
            _ActionButton(
              label: 'START DUTY',
              icon: dualMeter
                  ? Icons.av_timer
                  : hourMeter
                  ? Icons.timer_outlined
                  : Icons.speed_outlined,
              onPressed: canReadMeter
                  ? () => dualMeter
                        ? _showDualMeterDialog()
                        : hourMeter
                        ? _showHmrDialog()
                        : _showKmDialog()
                  : null,
            ),
            const SizedBox(height: 12),
            _ActionButton(
              label: 'EMERGENCY',
              icon: Icons.warning_amber,
              danger: true,
              onPressed: canCapture && !_busy ? _sendEmergency : null,
            ),
            if (_message != null) ...[
              const SizedBox(height: 16),
              _DriverFeedbackCard(
                message: _message!,
                onDismiss: () {
                  _messageTimer?.cancel();
                  setState(() => _message = null);
                },
              ),
            ],
          ] else ...[
            _ActionButton(
              label: 'EMERGENCY',
              icon: Icons.warning_amber,
              danger: true,
              prominent: true,
              onPressed: canCapture && !_busy ? _sendEmergency : null,
            ),
            const SizedBox(height: 12),
            if (capabilities.supportsTripComplete)
              Row(
                children: [
                  Expanded(
                    child: _ActionButton(
                      label: 'TRIP COMPLETE',
                      icon: Icons.check_circle_outline,
                      compact: true,
                      onPressed: canOperate ? _confirmTripComplete : null,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _ActionButton(
                      label: 'DIESEL',
                      icon: Icons.local_gas_station,
                      compact: true,
                      onPressed: canOperate ? _showDieselDialog : null,
                    ),
                  ),
                ],
              )
            else if (capabilities.supportsDiesel)
              _ActionButton(
                label: 'DIESEL',
                icon: Icons.local_gas_station,
                onPressed: canOperate ? _showDieselDialog : null,
              ),
            if (_message != null) ...[
              const SizedBox(height: 16),
              _DriverFeedbackCard(
                message: _message!,
                onDismiss: () {
                  _messageTimer?.cancel();
                  setState(() => _message = null);
                },
              ),
            ],
            const SizedBox(height: 12),
            if (assignment?.companyMaintenanceManaged == true)
              _DriverMaintenancePanel(
                items: _maintenanceItems,
                loading: _maintenanceLoading,
                busy: _busy,
                onOpen: _showMaintenanceItem,
              ),
            const SizedBox(height: 40),
            _ActionButton(
              label: 'END DUTY',
              icon: dualMeter
                  ? Icons.av_timer
                  : hourMeter
                  ? Icons.timer_outlined
                  : Icons.speed_outlined,
              onPressed: canReadMeter
                  ? () => dualMeter
                        ? _showDualMeterDialog(
                            forcedType: KmReadingType.endReading,
                          )
                        : hourMeter
                        ? _showHmrDialog(forcedType: KmReadingType.endReading)
                        : _showKmDialog(forcedType: KmReadingType.endReading)
                  : null,
            ),
          ],
        ],
      ),
    );
  }
}

class _DriverMaintenancePanel extends StatelessWidget {
  const _DriverMaintenancePanel({
    required this.items,
    required this.loading,
    required this.busy,
    required this.onOpen,
  });

  final List<DriverMaintenanceItem> items;
  final bool loading;
  final bool busy;
  final ValueChanged<DriverMaintenanceItem> onOpen;

  @override
  Widget build(BuildContext context) => Card(
    key: const Key('driver-maintenance-panel'),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.build_outlined),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'MAINTENANCE',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            loading
                ? 'Checking due work…'
                : '${items.length} item${items.length == 1 ? '' : 's'} due',
          ),
          if (!loading && items.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text('Nothing requires Maintenance attention.'),
            ),
          for (final item in items)
            ListTile(
              key: Key('driver-maintenance-${item.scheduleId}'),
              contentPadding: EdgeInsets.zero,
              title: Text(item.taskLabel.toUpperCase()),
              subtitle: Text(item.status == 'OVERDUE' ? 'Overdue' : 'Due now'),
              trailing: const Text('Upload proof'),
              onTap: busy ? null : () => onOpen(item),
            ),
        ],
      ),
    ),
  );
}

class DriverDiagnosticsScreen extends StatefulWidget {
  const DriverDiagnosticsScreen({required this.dependencies, super.key});

  final DriverAppDependencies dependencies;

  @override
  State<DriverDiagnosticsScreen> createState() =>
      _DriverDiagnosticsScreenState();
}

class _DriverDiagnosticsScreenState extends State<DriverDiagnosticsScreen> {
  int _pendingCount = 0;
  DateTime? _lastSuccessfulSync;
  String? _lastSyncError;
  String? _lastSyncErrorMessage;
  String? _lastSyncHttpStatus;
  String? _lastSyncErrorCode;
  String? _lastSyncFailureStage;
  List<Map<String, String>> _eventRows = const [];
  List<Map<String, String>> _dutyRows = const [];

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final sync = widget.dependencies.sync;
    final pendingCount = await sync.pendingCount();
    final lastSuccessfulSync = await sync.lastSuccessfulSync();
    final lastSyncError = await sync.lastSyncErrorCategory();
    final lastSyncErrorMessage = await sync.lastSyncErrorMessage();
    final lastSyncHttpStatus = await sync.lastSyncHttpStatus();
    final lastSyncErrorCode = await sync.lastSyncErrorCode();
    final lastSyncFailureStage = await sync.lastSyncFailureStage();
    final eventRows = isPilotBuild
        ? await sync.diagnosticEventRows()
        : const <Map<String, String>>[];
    final dutyRows = isPilotBuild
        ? await sync.diagnosticDutyRows()
        : const <Map<String, String>>[];
    if (!mounted) return;
    setState(() {
      _pendingCount = pendingCount;
      _lastSuccessfulSync = lastSuccessfulSync;
      _lastSyncError = lastSyncError;
      _lastSyncErrorMessage = lastSyncErrorMessage;
      _lastSyncHttpStatus = lastSyncHttpStatus;
      _lastSyncErrorCode = lastSyncErrorCode;
      _lastSyncFailureStage = lastSyncFailureStage;
      _eventRows = eventRows;
      _dutyRows = dutyRows;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Diagnostics')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const Text(
            'Support information',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),
          ListTile(
            title: const Text('App version'),
            subtitle: Text('$appVersion+$appBuild'),
          ),
          ListTile(
            title: const Text('Device registration ID'),
            subtitle: Text(widget.dependencies.installationIdentifier),
          ),
          ListTile(
            title: const Text('Pending local events'),
            subtitle: Text('$_pendingCount'),
          ),
          ListTile(
            title: const Text('Last successful sync'),
            subtitle: Text(
              _lastSuccessfulSync?.toLocal().toIso8601String() ??
                  'Not yet recorded',
            ),
          ),
          ListTile(
            title: const Text('Last sync error category'),
            subtitle: Text(_lastSyncError ?? 'None recorded'),
          ),
          if (_lastSyncErrorMessage != null)
            ListTile(
              title: const Text('Last sync error'),
              subtitle: Text(_lastSyncErrorMessage!),
            ),
          if (_lastSyncHttpStatus != null)
            ListTile(
              title: const Text('HTTP status'),
              subtitle: Text(_lastSyncHttpStatus!),
            ),
          if (_lastSyncErrorCode != null && _lastSyncErrorCode!.isNotEmpty)
            ListTile(
              title: const Text('Backend error code'),
              subtitle: Text(_lastSyncErrorCode!),
            ),
          if (_lastSyncFailureStage != null)
            ListTile(
              title: const Text('Failure stage'),
              subtitle: Text(_lastSyncFailureStage!),
            ),
          if (isPilotBuild) ...[
            ListTile(
              title: const Text('Fleet Manager Pilot'),
              subtitle: const Text('Version $appVersion · Build $appBuild'),
              trailing: widget.dependencies.pilotUpdater == null
                  ? null
                  : OutlinedButton(
                      onPressed: () => widget.dependencies.pilotUpdater!
                          .checkAndPresent(context, manual: true),
                      child: const Text('CHECK FOR UPDATES'),
                    ),
            ),
            const Divider(height: 32),
            _DiagnosticRows(
              title: 'Local event queue (safe)',
              emptyText: 'No local event rows.',
              rows: _eventRows,
            ),
            const SizedBox(height: 12),
            _DiagnosticRows(
              title: 'Local duty sessions (safe)',
              emptyText: 'No local duty snapshots.',
              rows: _dutyRows,
            ),
          ],
          const SizedBox(height: 12),
          const Text(
            'This screen contains no trip totals, credentials, or auth tokens.',
          ),
          const SizedBox(height: 12),
          OutlinedButton(
            onPressed: _load,
            child: const Text('REFRESH DIAGNOSTICS'),
          ),
        ],
      ),
    );
  }
}

class _DiagnosticRows extends StatelessWidget {
  const _DiagnosticRows({
    required this.title,
    required this.emptyText,
    required this.rows,
  });

  final String title;
  final String emptyText;
  final List<Map<String, String>> rows;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      initiallyExpanded: true,
      tilePadding: EdgeInsets.zero,
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
      subtitle: Text('${rows.length} row(s)'),
      children: [
        if (rows.isEmpty)
          Align(alignment: Alignment.centerLeft, child: Text(emptyText)),
        for (var index = 0; index < rows.length; index++)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: SelectableText(
                [
                  'row=${index + 1}',
                  for (final field in rows[index].entries)
                    '${field.key}=${field.value}',
                ].join('\n'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ),
      ],
    );
  }
}

class _AssignmentCard extends StatelessWidget {
  const _AssignmentCard({required this.assignment});

  final DriverAssignment? assignment;

  @override
  Widget build(BuildContext context) {
    if (assignment == null) {
      return Card(
        color: Theme.of(context).colorScheme.errorContainer,
        child: const Padding(
          padding: EdgeInsets.all(16),
          child: Text(
            'NO ACTIVE ASSIGNMENT\nEvents are disabled until a supervisor assigns an asset and site.',
          ),
        ),
      );
    }
    final shortName = assignment!.tipperShortName?.trim();
    final assetCode = assignment!.tipperAssetCode?.trim();
    final registration = assignment!.tipperRegistrationNumber?.trim();
    final title = shortName?.isNotEmpty == true
        ? shortName!
        : assetCode?.isNotEmpty == true
        ? assetCode!
        : registration?.isNotEmpty == true
        ? registration!
        : 'Assigned asset';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
            ),
            if (assetCode?.isNotEmpty == true && assetCode != title) ...[
              const SizedBox(height: 3),
              Text(
                assetCode!,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ],
            if (registration?.isNotEmpty == true &&
                registration != title &&
                registration != assetCode)
              Text(registration!, maxLines: 1, overflow: TextOverflow.ellipsis),
          ],
        ),
      ),
    );
  }
}

class _DriverStatePanel extends StatelessWidget {
  const _DriverStatePanel({
    required this.dutyStatusLabel,
    required this.dutyDetail,
    required this.pendingCount,
    this.correctionLabel,
    this.onCorrectStart,
    this.siteName,
  });

  final String dutyStatusLabel;
  final String dutyDetail;
  final String? siteName;
  final int pendingCount;
  final String? correctionLabel;
  final VoidCallback? onCorrectStart;

  @override
  Widget build(BuildContext context) {
    final synced = pendingCount == 0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  dutyStatusLabel == 'DUTY ACTIVE'
                      ? Icons.play_circle_outline
                      : Icons.pause_circle_outline,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        dutyStatusLabel,
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      if (siteName != null)
                        Text(
                          siteName!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      const SizedBox(height: 2),
                      Text(
                        dutyDetail,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                Chip(
                  avatar: Icon(
                    synced
                        ? Icons.cloud_done_outlined
                        : Icons.cloud_upload_outlined,
                    size: 16,
                  ),
                  label: Text(synced ? 'SYNCED' : '$pendingCount PENDING'),
                  backgroundColor: synced
                      ? Theme.of(context).colorScheme.primaryContainer
                      : Theme.of(context).colorScheme.tertiaryContainer,
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
            if (correctionLabel != null) ...[
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: onCorrectStart,
                  icon: const Icon(Icons.edit_outlined),
                  label: Text(correctionLabel!),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _DriverFeedbackCard extends StatelessWidget {
  const _DriverFeedbackCard({required this.message, required this.onDismiss});

  final String message;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final synced = message == 'Synced';
    return Card(
      color: synced
          ? Theme.of(context).colorScheme.primaryContainer
          : Theme.of(context).colorScheme.tertiaryContainer,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 4, 8),
        child: Row(
          children: [
            Icon(synced ? Icons.check_circle_outline : Icons.info_outline),
            const SizedBox(width: 10),
            Expanded(child: Text(message)),
            IconButton(
              tooltip: 'Dismiss message',
              visualDensity: VisualDensity.compact,
              onPressed: onDismiss,
              icon: const Icon(Icons.close),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.label,
    required this.icon,
    required this.onPressed,
    this.danger = false,
    this.prominent = false,
    this.compact = false,
  });

  final String label;
  final IconData icon;
  final VoidCallback? onPressed;
  final bool danger;
  final bool prominent;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: compact ? 82 : (prominent ? 78 : 72),
      child: FilledButton(
        onPressed: onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: danger
              ? Theme.of(context).colorScheme.errorContainer
              : Theme.of(context).colorScheme.surface,
          foregroundColor: danger
              ? Theme.of(context).colorScheme.onErrorContainer
              : Theme.of(context).colorScheme.primary,
          disabledBackgroundColor: Theme.of(
            context,
          ).colorScheme.surfaceContainerHighest,
          disabledForegroundColor: Theme.of(
            context,
          ).colorScheme.onSurfaceVariant,
          side: BorderSide(
            color: danger
                ? Theme.of(context).colorScheme.error
                : Theme.of(context).colorScheme.outline,
          ),
          padding: EdgeInsets.symmetric(horizontal: compact ? 8 : 18),
        ),
        child: compact
            ? Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(icon),
                  const SizedBox(height: 4),
                  FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      label,
                      maxLines: 1,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              )
            : Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(icon),
                  const SizedBox(width: 10),
                  Flexible(
                    child: Text(
                      label,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

class _KmCapture {
  const _KmCapture(this.type, this.value);

  final KmReadingType type;
  final String value;
}

class _DualMeterCapture {
  const _DualMeterCapture(this.odometerKm, this.hourMeter);

  final String odometerKm;
  final String hourMeter;
}

class _DualMeterDialog extends StatefulWidget {
  const _DualMeterDialog({required this.type});

  final KmReadingType type;

  @override
  State<_DualMeterDialog> createState() => _DualMeterDialogState();
}

class _DualMeterDialogState extends State<_DualMeterDialog> {
  final _km = TextEditingController();
  final _hours = TextEditingController();
  String? _error;

  bool _valid(String raw, double maximum) {
    final value = raw.trim();
    if (!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(value)) return false;
    final parsed = double.tryParse(value);
    return parsed != null &&
        parsed.isFinite &&
        parsed >= 0 &&
        parsed <= maximum;
  }

  @override
  void dispose() {
    _km.dispose();
    _hours.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final prefix = widget.type == KmReadingType.startReading ? 'START' : 'END';
    return AlertDialog(
      title: Text('$prefix READINGS'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _km,
            decoration: const InputDecoration(labelText: 'Odometer KM'),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            onChanged: (_) => setState(() => _error = null),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _hours,
            decoration: const InputDecoration(labelText: 'Hour Meter / HMR'),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            onChanged: (_) => setState(() => _error = null),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('CANCEL'),
        ),
        FilledButton(
          onPressed: () {
            if (!_valid(_km.text, maxOdometerKm) ||
                !_valid(_hours.text, maxHourMeterHours)) {
              setState(
                () => _error =
                    'Enter both valid readings. Neither meter is optional for this asset.',
              );
              return;
            }
            Navigator.pop(
              context,
              _DualMeterCapture(_km.text.trim(), _hours.text.trim()),
            );
          },
          child: const Text('CONTINUE'),
        ),
      ],
    );
  }
}

class _KmDialog extends StatefulWidget {
  const _KmDialog({required this.type, this.hourMeter = false});

  final KmReadingType type;
  final bool hourMeter;

  @override
  State<_KmDialog> createState() => _KmDialogState();
}

class _KmDialogState extends State<_KmDialog> {
  final _value = TextEditingController();
  String? _error;

  String? _validateReading(String raw) {
    final value = raw.trim();
    if (!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(value)) {
      return widget.hourMeter
          ? invalidHourMeterMessage
          : invalidOdometerMessage;
    }
    final parsed = double.tryParse(value);
    if (parsed == null ||
        !parsed.isFinite ||
        parsed < 0 ||
        parsed > (widget.hourMeter ? maxHourMeterHours : maxOdometerKm)) {
      return widget.hourMeter
          ? invalidHourMeterMessage
          : invalidOdometerMessage;
    }
    return null;
  }

  @override
  void dispose() {
    _value.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.hourMeter ? 'HMR READING' : 'KM READING'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            widget.type == KmReadingType.startReading
                ? 'START ${widget.hourMeter ? 'HMR' : 'KM'}'
                : 'END ${widget.hourMeter ? 'HMR' : 'KM'}',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          TextField(
            controller: _value,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            onChanged: (_) {
              if (_error != null) setState(() => _error = null);
            },
            decoration: InputDecoration(
              labelText: widget.hourMeter ? 'Hours' : 'Kilometres',
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('CANCEL'),
        ),
        FilledButton(
          onPressed: () {
            final error = _validateReading(_value.text);
            if (error != null) {
              setState(() => _error = error);
              return;
            }
            Navigator.pop(context, _KmCapture(widget.type, _value.text.trim()));
          },
          child: const Text('CONTINUE'),
        ),
      ],
    );
  }
}

class _DieselDialog extends StatefulWidget {
  const _DieselDialog();

  @override
  State<_DieselDialog> createState() => _DieselDialogState();
}

class _DieselDialogState extends State<_DieselDialog> {
  final _litres = TextEditingController();

  @override
  void dispose() {
    _litres.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('DIESEL'),
      content: TextField(
        controller: _litres,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: const InputDecoration(labelText: 'Litres'),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('CANCEL'),
        ),
        FilledButton(
          onPressed: () {
            final value = double.tryParse(_litres.text.trim());
            if (value == null || value <= 0) return;
            Navigator.pop(context, _litres.text.trim());
          },
          child: const Text('CONTINUE'),
        ),
      ],
    );
  }
}

class _UnavailableScreen extends StatelessWidget {
  const _UnavailableScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Text('Driver client dependencies are not initialized.'),
      ),
    );
  }
}
