package com.vivy.node.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.vivy.node.connection.HubConnectionManager
import com.vivy.node.discovery.DiscoveryManager
import com.vivy.node.security.CredentialManager
import com.vivy.node.camera.CameraCaptureManager

import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.rememberDrawerState
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.IconButton
import androidx.compose.material3.ExperimentalMaterial3Api
import kotlinx.coroutines.launch

data class NavItem(
    val route: String,
    val label: String,
    val icon: ImageVector
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MultimodalApp(
    connectionManager: HubConnectionManager,
    discoveryManager: DiscoveryManager,
    credentialManager: CredentialManager,
    cameraCaptureManager: CameraCaptureManager
) {
    val navController = rememberNavController()
    val drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    val navItems = listOf(
        NavItem("home", "Home", Icons.Filled.Home),
        NavItem("chat", "Chat", Icons.Filled.Email),
        NavItem("voice", "Voice", Icons.Filled.PlayArrow),
        NavItem("screen", "Screen Sharing", Icons.Filled.Share),
        NavItem("avatar", "Avatar", Icons.Filled.Person),
        NavItem("voice_cloning", "Voice Cloning", Icons.Filled.Build)
    )

    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet {
                Spacer(Modifier.height(12.dp))
                navItems.forEach { item ->
                    NavigationDrawerItem(
                        icon = { Icon(item.icon, contentDescription = item.label) },
                        label = { Text(item.label) },
                        selected = currentRoute == item.route,
                        onClick = {
                            scope.launch { drawerState.close() }
                            navController.navigate(item.route) {
                                popUpTo(navController.graph.startDestinationId)
                                launchSingleTop = true
                            }
                        },
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp)
                    )
                }
            }
        }
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text("Vivy Hub Node") },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Icon(Icons.Filled.Menu, contentDescription = "Menu")
                        }
                    }
                )
            }
        ) { innerPadding ->
            NavHost(
                navController = navController,
                startDestination = "home",
                modifier = Modifier.padding(innerPadding)
            ) {
                composable("home") {
                    DashboardScreen(connectionManager, discoveryManager, credentialManager, cameraCaptureManager)
                }
                composable("chat") {
                    ChatScreen(connectionManager)
                }
                composable("voice") {
                    VoiceScreen(connectionManager)
                }
                composable("screen") {
                    ScreenSharingScreen(connectionManager)
                }
                composable("avatar") {
                    AvatarScreen(connectionManager)
                }
                composable("voice_cloning") {
                    VoiceCloningScreen(connectionManager)
                }
            }
        }
    }
}
