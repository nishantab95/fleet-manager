import 'dart:async';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import 'data/api_client.dart';
import 'data/secure_session_store.dart';
import 'data/sync_engine.dart';
import 'domain/driver_models.dart';
import 'domain/role_models.dart';
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

class DriverAppDependencies {
  const DriverAppDependencies({
    required this.api,
    required this.sessionStore,
    required this.sync,
    required this.installationIdentifier,
  });

  final ApiClient api;
  final SecureSessionStore sessionStore;
  final SyncEngine sync;
  final String installationIdentifier;
}

class FleetManagerApp extends StatelessWidget {
  const FleetManagerApp({super.key, this.dependencies});

  final DriverAppDependencies? dependencies;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Fleet Manager',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF155E63),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFF7F9F8),
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(),
          filled: true,
          fillColor: Colors.white,
        ),
      ),
      home: dependencies == null
          ? const _UnavailableScreen()
          : DriverSessionScreen(dependencies: dependencies!),
    );
  }
}

class DriverSessionScreen extends StatefulWidget {
  const DriverSessionScreen({required this.dependencies, super.key});

  final DriverAppDependencies dependencies;

  @override
  State<DriverSessionScreen> createState() => _DriverSessionScreenState();
}

class _DriverSessionScreenState extends State<DriverSessionScreen> {
  DriverAssignment? _assignment;
  DriverDutyState _duty = const DriverDutyState.none();
  String? _role;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_restoreSession());
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
        try {
          await api.registerDevice(
            installationIdentifier: widget.dependencies.installationIdentifier,
          );
        } on ApiException catch (error) {
          if (error.isUnauthorized) rethrow;
        }
        try {
          assignment = await api.currentAssignment();
          if (assignment == null) {
            assignment = await widget.dependencies.sync.localAssignment();
            if (assignment != null) {
              duty = await widget.dependencies.sync.localDutyState(
                assignment.assignmentId,
              );
            }
          } else {
            duty = await api.currentDuty();
            duty = await widget.dependencies.sync.effectiveDuty(
              assignment.assignmentId,
              duty,
            );
          }
        } on ApiException catch (error) {
          if (error.isUnauthorized) rethrow;
          assignment = await widget.dependencies.sync.localAssignment();
          if (assignment == null) rethrow;
          duty = await widget.dependencies.sync.localDutyState(
            assignment.assignmentId,
          );
        }
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
      api.clearSession();
      await widget.dependencies.sessionStore.clear();
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _signedIn(SessionTokens tokens) async {
    DriverAssignment? assignment;
    var duty = const DriverDutyState.none();
    if (tokens.role == 'DRIVER') {
      try {
        assignment = await widget.dependencies.api.currentAssignment();
        if (assignment == null) {
          assignment = await widget.dependencies.sync.localAssignment();
          if (assignment != null) {
            duty = await widget.dependencies.sync.localDutyState(
              assignment.assignmentId,
            );
          }
        } else {
          duty = await widget.dependencies.api.currentDuty();
          duty = await widget.dependencies.sync.effectiveDuty(
            assignment.assignmentId,
            duty,
          );
        }
      } on ApiException catch (error) {
        if (error.isUnauthorized) rethrow;
        assignment = await widget.dependencies.sync.localAssignment();
        if (assignment == null) rethrow;
        duty = await widget.dependencies.sync.localDutyState(
          assignment.assignmentId,
        );
      }
    }
    if (!mounted) return;
    setState(() {
      _assignment = assignment;
      _duty = duty;
      _role = tokens.role;
      _error = null;
    });
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
    await widget.dependencies.sessionStore.save(tokens);
    if (tokens.role == 'DRIVER') {
      await widget.dependencies.api.registerDevice(
        installationIdentifier: widget.dependencies.installationIdentifier,
      );
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
          title: const Text('Pilot server'),
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
    required this.onSignOut,
    super.key,
  });

  final DriverAppDependencies dependencies;
  final DriverAssignment? assignment;
  final DriverDutyState duty;
  final Future<void> Function() onSignOut;

  @override
  State<DriverHomeScreen> createState() => _DriverHomeScreenState();
}

class _DriverHomeScreenState extends State<DriverHomeScreen> {
  final _picker = ImagePicker();
  int _pendingCount = 0;
  late DriverDutyState _duty;
  String? _message;
  bool _busy = false;
  DateTime? _lastQueuedAt;
  DriverEventType? _lastQueuedEventType;

  @override
  void initState() {
    super.initState();
    _duty = widget.duty;
    unawaited(_refreshQueue());
    unawaited(_refreshDuty());
  }

  @override
  void didUpdateWidget(covariant DriverHomeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.duty.status != widget.duty.status ||
        oldWidget.duty.sessionId != widget.duty.sessionId ||
        oldWidget.duty.localState != widget.duty.localState) {
      _duty = widget.duty;
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
      await _refreshDuty();
      final syncError = await widget.dependencies.sync.lastSyncErrorMessage();
      final pending = await widget.dependencies.sync.pendingCount();
      if (mounted) {
        setState(() {
          _message = pending > 0
              ? (syncError == null
                    ? '$pending event(s) pending. Retry when connected.'
                    : 'Needs attention: $syncError')
              : 'Synced';
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _queue(
    DriverEventType eventType, {
    Map<String, dynamic> payload = const <String, dynamic>{},
    String? evidencePath,
  }) async {
    if (_busy) return;
    final assignment = widget.assignment;
    if (assignment == null) return;
    final now = DateTime.now();
    if (_lastQueuedEventType == eventType &&
        _lastQueuedAt != null &&
        now.difference(_lastQueuedAt!) < const Duration(milliseconds: 500)) {
      return;
    }
    _lastQueuedAt = now;
    _lastQueuedEventType = eventType;
    setState(() => _busy = true);
    try {
      await widget.dependencies.sync.enqueue(
        assignment: assignment,
        eventType: eventType,
        payload: payload,
        evidencePath: evidencePath,
      );
      await _refreshQueue();
      if (eventType == DriverEventType.kmReading) await _refreshDuty();
      if (mounted) {
        final label = switch (eventType) {
          DriverEventType.tripComplete => 'Trip recorded',
          DriverEventType.diesel => 'Diesel recorded',
          DriverEventType.emergency => 'Emergency alert sent.',
          DriverEventType.kmReading => 'KM reading saved',
        };
        setState(() => _message = label);
      }
      unawaited(_syncQueuedEvents());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _syncQueuedEvents() async {
    if (widget.dependencies.api.session == null) return;
    try {
      await widget.dependencies.sync.syncPending();
      await _refreshQueue();
      await _refreshDuty();
    } catch (_) {
      // Offline queue errors remain visible through the pending count and
      // diagnostics; the local operational state must stay available.
    }
  }

  Future<void> _showKmDialog() async {
    final result = await showDialog<_KmCapture>(
      context: context,
      builder: (context) => _KmDialog(
        type: _duty.canEnd
            ? KmReadingType.endReading
            : KmReadingType.startReading,
      ),
    );
    if (result == null) {
      return;
    }
    final photo = await _pickEvidence(mustChoose: true);
    if (photo == null) {
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

  Future<void> _sendEmergency() => _queue(DriverEventType.emergency);

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
    return _picker.pickImage(source: source, imageQuality: 85);
  }

  @override
  Widget build(BuildContext context) {
    final assignment = widget.assignment;
    final canCapture = assignment != null;
    final canOperate = canCapture && !_busy && _duty.isOperationallyActive;
    final canReadKm = canCapture && !_busy && _duty.canReadKm;
    final dutyLabel = switch (_duty.localState) {
      LocalDutyState.startPendingSync => 'Saved on phone · Syncing start',
      LocalDutyState.activeConfirmed => 'Duty active',
      LocalDutyState.endPendingSync => 'Saving end KM…',
      LocalDutyState.closedConfirmed =>
        'Previous duty completed · Record START KM for the next session',
      LocalDutyState.needsAttention =>
        'START KM needs correction. Please check the reading.',
      null => switch (_duty.status) {
        DriverDutyStatus.none => 'Before START KM',
        DriverDutyStatus.active => 'Duty active',
        DriverDutyStatus.closed =>
          'Previous duty completed · Record START KM for the next session',
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
        padding: const EdgeInsets.all(20),
        children: [
          _AssignmentCard(assignment: assignment),
          const SizedBox(height: 20),
          Text(
            _pendingCount == 0
                ? 'Synced'
                : '$_pendingCount event(s) pending sync',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Text(dutyLabel, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          GridView.count(
            crossAxisCount: 2,
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: 1.42,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            children: [
              _ActionButton(
                label: 'TRIP COMPLETE',
                icon: Icons.check_circle_outline,
                onPressed: canOperate
                    ? () => _queue(DriverEventType.tripComplete)
                    : null,
              ),
              _ActionButton(
                label: 'KM READING',
                icon: Icons.speed,
                onPressed: canReadKm ? _showKmDialog : null,
              ),
              _ActionButton(
                label: 'DIESEL',
                icon: Icons.local_gas_station,
                onPressed: canOperate ? _showDieselDialog : null,
              ),
              _ActionButton(
                label: 'EMERGENCY',
                icon: Icons.warning_amber,
                danger: true,
                onPressed: canCapture && !_busy ? _sendEmergency : null,
              ),
            ],
          ),
          if (_message != null) ...[
            const SizedBox(height: 16),
            Text(_message!, textAlign: TextAlign.center),
          ],
        ],
      ),
    );
  }
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
    if (!mounted) return;
    setState(() {
      _pendingCount = pendingCount;
      _lastSuccessfulSync = lastSuccessfulSync;
      _lastSyncError = lastSyncError;
      _lastSyncErrorMessage = lastSyncErrorMessage;
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
            'NO ACTIVE ASSIGNMENT\nEvents are disabled until a supervisor assigns a tipper and site.',
          ),
        ),
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              assignment!.tipperShortName ??
                  assignment!.tipperRegistrationNumber,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 4),
            Text(assignment!.tipperRegistrationNumber),
            Text('Site: ${assignment!.siteName}'),
            Text('Supervisor: ${assignment!.supervisorName}'),
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
  });

  final String label;
  final IconData icon;
  final VoidCallback? onPressed;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: SizedBox(
        height: 64,
        child: FilledButton.icon(
          onPressed: onPressed,
          style: danger
              ? FilledButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.error,
                )
              : null,
          icon: Icon(icon),
          label: Text(
            label,
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
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

class _KmDialog extends StatefulWidget {
  const _KmDialog({required this.type});

  final KmReadingType type;

  @override
  State<_KmDialog> createState() => _KmDialogState();
}

class _KmDialogState extends State<_KmDialog> {
  final _value = TextEditingController();
  String? _error;

  String? _validateOdometer(String raw) {
    final value = raw.trim();
    if (!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(value)) {
      return invalidOdometerMessage;
    }
    final parsed = double.tryParse(value);
    if (parsed == null ||
        !parsed.isFinite ||
        parsed < 0 ||
        parsed > maxOdometerKm) {
      return invalidOdometerMessage;
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
      title: const Text('KM READING'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            widget.type == KmReadingType.startReading ? 'START KM' : 'END KM',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          TextField(
            controller: _value,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            onChanged: (_) {
              if (_error != null) setState(() => _error = null);
            },
            decoration: const InputDecoration(labelText: 'Kilometres'),
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
            final error = _validateOdometer(_value.text);
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
